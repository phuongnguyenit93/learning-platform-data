# Dừng sớm bằng lọc và giới hạn luồng khung StackWalker

Java 9 giới thiệu **StackWalker** để duyệt các stack frame của luồng hiện tại. Khi cần tìm một frame cụ thể hoặc chỉ lấy một số frame đầu tiên, có thể kết hợp **filter()**, **limit()** và các thao tác kết thúc có khả năng dừng sớm như **findFirst()** hoặc **anyMatch()**.

Cách làm này giúp chương trình chỉ xử lý phần stack cần thiết. Thay vì chuyển toàn bộ stack thành mảng rồi lọc, StackWalker cung cấp một Stream<StackWalker.StackFrame> để xây dựng pipeline lazy và chỉ duyệt đến khi kết quả đã được xác định.

## 1. StackWalker và StackFrame

**StackWalker** là API trong package java.lang, có từ Java 9. Nó cho phép truy vấn stack trace của thread đang thực thi lời gọi walk().

Mỗi phần tử trong luồng là một **StackWalker.StackFrame**, mô tả một frame trên call stack. Một frame thường chứa:

| Phương thức | Thông tin |
|---|---|
| getClassName() | Tên đầy đủ của lớp chứa frame |
| getMethodName() | Tên phương thức |
| getFileName() | Tên file nguồn nếu có |
| getLineNumber() | Số dòng nguồn nếu có |
| isNativeMethod() | Frame có đại diện cho phương thức native hay không |
| toStackTraceElement() | Chuyển frame thành StackTraceElement |

Khởi tạo StackWalker mặc định:

~~~java
StackWalker walker = StackWalker.getInstance();
~~~

StackWalker chỉ duyệt stack của thread gọi walk(). Nếu muốn lấy stack của một thread khác, không thể dùng instance này để đọc trực tiếp stack đó.

Stream frame có thứ tự từ frame hiện tại ở đỉnh stack đi dần xuống các caller. Vì vậy, findFirst() thường trả về frame gần vị trí gọi walk() nhất sau khi áp dụng bộ lọc.

## 2. walk() cung cấp Stream trong phạm vi callback

Phương thức trung tâm có dạng:

~~~java
<T> T walk(Function<? super Stream<StackFrame>, ? extends T> function)
~~~

Truyền vào walk() một hàm nhận Stream<StackFrame> và trả về kết quả T. Pipeline nên được xây dựng và kết thúc ngay trong callback:

~~~java
String methodName = walker.walk(frames ->
        frames
                .map(StackWalker.StackFrame::getMethodName)
                .findFirst()
                .orElse("<empty>"));
~~~

Có hai quy tắc quan trọng:

- Stream được cung cấp cho callback chỉ dùng trong thời gian callback đang chạy. StackWalker đóng stream sau khi callback trả về.
- Không trả Stream ra ngoài callback để xử lý về sau hoặc lưu nó vào field. Hãy trả về dữ liệu đã thu được như String, boolean, List hoặc Optional.

Terminal operation phải chạy bên trong callback. Ví dụ findFirst(), anyMatch() và collect() đều trả về kết quả có thể sử dụng sau khi walk() kết thúc.

## 3. filter(): chỉ giữ những frame cần tìm

filter() là intermediate operation, dùng predicate để chọn frame:

~~~java
Optional<StackWalker.StackFrame> firstApplicationFrame =
        walker.walk(frames -> frames
                .filter(frame ->
                        frame.getClassName().startsWith("com.example."))
                .findFirst());
~~~

Ví dụ trên chỉ giữ frame có class name bắt đầu bằng package com.example rồi lấy frame đầu tiên.

Có thể kết hợp nhiều điều kiện:

~~~java
Optional<String> callerMethod = walker.walk(frames -> frames
        .filter(frame -> frame.getClassName().equals("com.example.OrderService"))
        .filter(frame -> !frame.getMethodName().equals("loadOrder"))
        .map(StackWalker.StackFrame::getMethodName)
        .findFirst());
~~~

Trong ví dụ, frame hiện tại của loadOrder() bị loại bỏ; frame tiếp theo trong OrderService được chọn nếu tồn tại.

Nên lọc bằng cả tên lớp và tên phương thức khi cần xác định một vị trí cụ thể. Chỉ lọc theo method name có thể chọn nhầm phương thức trùng tên ở lớp khác.

filter() là lazy: predicate chỉ được đánh giá khi terminal operation tiêu thụ stream. Chỉ gọi filter() mà không có terminal operation sẽ không duyệt stack.

## 4. limit(): giới hạn số frame được xử lý

limit(n) giữ tối đa n phần tử đầu tiên của stream:

~~~java
List<String> methods = walker.walk(frames -> frames
        .limit(5)
        .map(StackWalker.StackFrame::getMethodName)
        .collect(Collectors.toList()));
~~~

Ví dụ lấy tối đa năm method name gần đỉnh stack. Nếu stack còn ít hơn năm frame, danh sách kết quả sẽ ngắn hơn.

Vị trí đặt limit() làm thay đổi ý nghĩa:

**Lọc trước, giới hạn sau:**

~~~java
frames
        .filter(frame -> frame.getClassName().startsWith("com.example."))
        .limit(3)
        .collect(Collectors.toList());
~~~

Kết quả có tối đa ba frame đầu tiên thỏa điều kiện lọc, dù phải duyệt qua nhiều frame không khớp trước đó.

**Giới hạn trước, lọc sau:**

~~~java
frames
        .limit(3)
        .filter(frame -> frame.getClassName().startsWith("com.example."))
        .collect(Collectors.toList());
~~~

Chỉ xét ba frame đầu tiên của toàn stack rồi mới lọc. Nếu ba frame đó không khớp, kết quả có thể rỗng dù phía dưới còn frame phù hợp.

Hãy đặt filter() trước limit() khi mục tiêu là tìm n frame phù hợp đầu tiên trong toàn stack.

limit() là intermediate operation. Bản thân nó không thực thi pipeline; terminal operation phía sau mới kích hoạt việc duyệt.

## 5. Các terminal operation có thể dừng sớm

Một số terminal operation kết thúc ngay khi đã xác định được kết quả:

| Terminal operation | Điều kiện dừng |
|---|---|
| findFirst() | Tìm thấy phần tử đầu tiên |
| findAny() | Tìm thấy một phần tử bất kỳ |
| anyMatch(predicate) | Có ít nhất một phần tử thỏa điều kiện |
| allMatch(predicate) | Có phần tử đầu tiên không thỏa điều kiện, hoặc đã duyệt hết |
| noneMatch(predicate) | Có phần tử đầu tiên thỏa điều kiện, hoặc đã duyệt hết |

Ví dụ kiểm tra stack có chứa phương thức main hay không:

~~~java
boolean hasMain = walker.walk(frames ->
        frames.anyMatch(frame ->
                frame.getMethodName().equals("main")));
~~~

Nếu tìm thấy frame main, anyMatch() trả true và không cần kiểm tra các frame còn lại.

Ví dụ tìm frame đầu tiên thuộc một package:

~~~java
Optional<String> firstApplicationMethod = walker.walk(frames -> frames
        .filter(frame -> frame.getClassName().startsWith("com.example."))
        .map(StackWalker.StackFrame::getMethodName)
        .findFirst());
~~~

findFirst() tận dụng thứ tự stack để dừng sau frame phù hợp đầu tiên.

Ngược lại, các terminal operation như collect(), forEach() hoặc count() thường phải tiêu thụ toàn bộ phần stream còn lại, trừ khi pipeline đã có limit() hoặc một điều kiện khác làm giảm số phần tử.

## 6. Kết hợp filter(), limit() và short-circuit

Một pipeline thường có dạng:

~~~java
List<String> firstMethods = walker.walk(frames -> frames
        .filter(frame -> frame.getClassName().startsWith("com.example."))
        .limit(5)
        .map(StackWalker.StackFrame::getMethodName)
        .collect(Collectors.toList()));
~~~

Các bước được thực hiện theo thứ tự:

1. StackWalker cung cấp frame theo thứ tự từ hiện tại ra caller.
2. filter() loại bỏ frame không thuộc package cần quan sát.
3. limit(5) ngừng yêu cầu thêm frame sau khi đã nhận đủ năm frame phù hợp.
4. map() chuyển frame thành tên phương thức.
5. collect() tạo danh sách chứa kết quả.

Pipeline chỉ duyệt đủ frame để thu được năm frame phù hợp hoặc đến khi stack kết thúc. Nếu cần đúng một kết quả, dùng findFirst() thay vì collect().

Có thể dùng skip(n) để bỏ qua một số frame đầu, chẳng hạn bỏ qua frame helper của chính tiện ích stack inspection:

~~~java
Optional<String> caller = walker.walk(frames -> frames
        .skip(1)
        .map(StackWalker.StackFrame::getMethodName)
        .findFirst());
~~~

skip(1) bỏ qua đúng một frame trong stream trước khi tìm phần tử tiếp theo. Nếu call path thay đổi, vị trí helper có thể thay đổi; lọc theo class và method thường rõ nghĩa hơn khi cần loại bỏ một frame cụ thể.

## 7. Lấy Class object khi cần lọc theo kiểu

Mặc định StackWalker cung cấp tên lớp qua getClassName(). Nếu cần thao tác trực tiếp với Class<?> hoặc dùng phép so sánh class object, tạo walker với option RETAIN_CLASS_REFERENCE:

~~~java
StackWalker walker = StackWalker.getInstance(
        StackWalker.Option.RETAIN_CLASS_REFERENCE);
~~~

Sau đó có thể gọi getDeclaringClass():

~~~java
Optional<Class<?>> declaringClass = walker.walk(frames -> frames
        .filter(frame -> frame.getMethodName().equals("handle"))
        .findFirst()
        .map(StackWalker.StackFrame::getDeclaringClass));
~~~

Nếu không bật RETAIN_CLASS_REFERENCE, gọi getDeclaringClass() có thể ném UnsupportedOperationException. Khi chỉ cần lọc theo tên lớp, getClassName() là đủ và không cần bật option này.

StackWalker cũng có các option SHOW_REFLECT_FRAMES và SHOW_HIDDEN_FRAMES để thay đổi việc hiển thị frame phản chiếu hoặc frame ẩn. Mặc định các frame này không được hiển thị. Chỉ bật khi công cụ chẩn đoán thực sự cần quan sát chúng.

## 8. Ví dụ hoàn chỉnh: tìm caller và lấy ba frame phù hợp đầu tiên

Lưu chương trình dưới tên **StackWalkerFilteringDemo.java**. Ví dụ tạo một call path gồm main(), entry(), service() và repository(). Khi walk() được gọi trong repository(), frame hiện tại là repository; caller gần nhất là service.

~~~java
import java.util.List;
import java.util.stream.Collectors;

public class StackWalkerFilteringDemo {
    private static final String CLASS_NAME =
            StackWalkerFilteringDemo.class.getName();
    private static final StackWalker WALKER = StackWalker.getInstance();

    public static void main(String[] args) {
        new StackWalkerFilteringDemo().entry();
    }

    private void entry() {
        service();
    }

    private void service() {
        repository();
    }

    private void repository() {
        String firstCaller = WALKER.walk(frames -> frames
                .filter(frame -> frame.getClassName().equals(CLASS_NAME))
                .filter(frame -> !frame.getMethodName().equals("repository"))
                .map(StackWalker.StackFrame::getMethodName)
                .findFirst()
                .orElse("<none>"));

        boolean mainIsOnStack = WALKER.walk(frames ->
                frames.anyMatch(frame ->
                        frame.getClassName().equals(CLASS_NAME)
                                && frame.getMethodName().equals("main")));

        List<String> firstThreeMethods = WALKER.walk(frames -> frames
                .filter(frame -> frame.getClassName().equals(CLASS_NAME))
                .limit(3)
                .map(StackWalker.StackFrame::getMethodName)
                .collect(Collectors.toList()));

        System.out.println("first matching caller: " + firstCaller);
        System.out.println("main is on current stack: " + mainIsOnStack);
        System.out.println("first three methods: " + firstThreeMethods);
    }
}
~~~

Biên dịch và chạy với Java 9 trở lên:

~~~bash
javac --release 9 StackWalkerFilteringDemo.java
java StackWalkerFilteringDemo
~~~

Kết quả stdout trong môi trường chạy ví dụ:

~~~text
first matching caller: service
main is on current stack: true
first three methods: [repository, service, entry]
~~~

Giải thích:

- filter() giữ frame thuộc StackWalkerFilteringDemo.
- Điều kiện thứ hai loại frame repository hiện tại; findFirst() trả về caller phù hợp đầu tiên là service.
- anyMatch() dừng khi tìm thấy frame main.
- filter(...).limit(3) lấy ba method đầu tiên thuộc lớp ví dụ; collect() chuyển chúng thành List.
- Không pipeline nào trả Stream ra ngoài callback walk().

## 9. Lỗi thường gặp và cách tránh

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ gọi filter() mà không có terminal operation | Pipeline lazy nên chưa duyệt frame nào | Kết thúc bằng findFirst(), anyMatch(), collect() hoặc terminal operation phù hợp |
| Dùng collect() khi chỉ cần frame đầu tiên | Duyệt nhiều frame hơn cần thiết | Dùng findFirst() hoặc anyMatch() để short-circuit |
| Đặt limit() trước filter() khi muốn lấy n frame khớp | Chỉ lọc trong n frame đầu của toàn stack | Đặt filter() trước limit() |
| Nghĩ limit() tự chạy pipeline | Không có kết quả vì limit() chỉ là intermediate operation | Thêm terminal operation phía sau |
| Trả Stream ra ngoài callback walk() | Stream đã bị đóng sau khi callback kết thúc | Trả về dữ liệu đã materialize như Optional, String, boolean hoặc List |
| Chỉ lọc theo method name | Có thể chọn nhầm phương thức cùng tên ở lớp khác | Kết hợp getClassName() với getMethodName() |
| Gọi getDeclaringClass() trên walker mặc định | Có thể nhận UnsupportedOperationException | Tạo walker với RETAIN_CLASS_REFERENCE |
| Dùng StackWalker để đọc stack thread khác | Chỉ nhận stack của thread đang gọi walk() | Thực hiện walk() trên chính thread cần quan sát |

## 10. Ghi nhớ

- StackWalker có từ Java 9 và cung cấp Stream<StackFrame> theo thứ tự từ frame hiện tại đến caller.
- walk() truyền stream vào callback; stream được đóng khi callback kết thúc.
- filter(), map(), skip() và limit() là intermediate operation, được thực thi lazy.
- findFirst(), anyMatch() và một số terminal operation khác có thể dừng duyệt sớm khi đã đủ kết quả.
- filter().limit(n) lấy tối đa n frame phù hợp; limit(n).filter() chỉ lọc trong n frame đầu.
- Dùng findFirst() khi chỉ cần frame phù hợp đầu tiên; dùng anyMatch() khi chỉ cần câu trả lời boolean.
- Không giữ Stream để dùng sau callback; hãy trả về kết quả đã thu được.
- Bật RETAIN_CLASS_REFERENCE khi cần Class<?> qua getDeclaringClass(); chỉ dùng getClassName() nếu cần tên lớp.
- Chọn pipeline ngắn nhất đáp ứng nhu cầu để tránh duyệt stack không cần thiết.
