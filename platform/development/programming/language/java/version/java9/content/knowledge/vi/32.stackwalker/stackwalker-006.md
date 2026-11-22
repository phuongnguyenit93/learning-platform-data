# getCallerClass và lựa chọn khung gọi với StackWalker

## Mục tiêu

Sau bài học này, bạn có thể:

- Dùng \`StackWalker.getCallerClass()\` để lấy class của caller trực tiếp.
- Hiểu vì sao phải bật \`RETAIN_CLASS_REFERENCE\` khi cần đối tượng \`Class<?>\`.
- Chọn một khung gọi cụ thể bằng \`walk\`, \`filter\`, \`skip\` và \`findFirst\`.
- Phân biệt caller trực tiếp với caller nhìn thấy từ bên trong một helper method.
- Quyết định khi nào cần hiển thị reflection frame hoặc hidden frame.
- Tránh dùng thông tin stack làm định danh hoặc cơ chế phân quyền bảo mật.

## 1. getCallerClass() trả về class nào?

Java 9 bổ sung \`StackWalker.getCallerClass()\` để lấy class của caller trực tiếp của method đang gọi API. Method này phù hợp khi bạn chỉ cần biết thành phần nào đã gọi method hiện tại và không cần tự duyệt toàn bộ stack.

Ví dụ, nếu chuỗi lời gọi là:

~~~text
Client.start()
  -> Service.load()
      -> Repository.read()
~~~

Khi \`Repository.read()\` gọi \`walker.getCallerClass()\`, kết quả là class \`Service\`, vì \`Service.load()\` là caller trực tiếp của \`Repository.read()\`.

Khởi tạo walker với tùy chọn giữ tham chiếu class:

~~~java
private static final StackWalker WALKER =
        StackWalker.getInstance(StackWalker.Option.RETAIN_CLASS_REFERENCE);
~~~

Sau đó gọi:

~~~java
Class<?> caller = WALKER.getCallerClass();
System.out.println(caller.getName());
~~~

Nếu walker không được tạo với \`RETAIN_CLASS_REFERENCE\`, lời gọi \`getCallerClass()\` ném \`IllegalCallerException\`. Tùy chọn này cũng cho phép lấy \`Class<?>\` từ \`StackFrame.getDeclaringClass()\`.

Khi chỉ cần tên class, có thể dùng \`StackFrame.getClassName()\` trong \`walk\` mà không cần giữ tham chiếu class.

## 2. Caller trực tiếp khác với class đang chạy method

Một nhầm lẫn thường gặp là nghĩ \`getCallerClass()\` trả về class chứa lời gọi API. Thực tế, nó trả về class của caller của method đang gọi API.

Trong ví dụ:

~~~java
class Repository {
    static void read() {
        Class<?> caller = WALKER.getCallerClass();
    }
}
~~~

- Class chứa \`read()\` là \`Repository\`.
- Caller trực tiếp của \`read()\` có thể là \`Service\`.
- \`getCallerClass()\` trả về \`Service\`.

Điều này đặc biệt quan trọng khi bọc thao tác lấy caller trong một helper:

~~~java
class CallerTools {
    static Class<?> immediateCaller() {
        return WALKER.getCallerClass();
    }
}
~~~

Nếu \`Repository.read()\` gọi \`CallerTools.immediateCaller()\`, kết quả là \`Repository\`, bởi vì \`Repository.read()\` hiện là caller trực tiếp của method helper. Nó không tự động bỏ qua helper để trả về \`Service\`.

Nếu API của bạn cần tìm caller bên ngoài một hoặc nhiều lớp tiện ích, hãy dùng \`walk\` để chọn frame theo quy tắc rõ ràng.

## 3. Duyệt stack bằng walk()

\`StackWalker.walk(Function<Stream<StackFrame>, T>)\` cho phép xử lý stream các stack frame trong một callback:

~~~java
String methods = WALKER.walk(frames ->
        frames.limit(4)
              .map(StackWalker.StackFrame::getMethodName)
              .collect(Collectors.joining(" -> ")));
~~~

Các điểm cần nhớ:

- Frame đầu tiên thường là method hiện tại đang gọi \`walk\`.
- Frame tiếp theo là caller của method đó, sau đó là các caller ở cao hơn.
- \`filter(predicate)\` chọn các frame thỏa điều kiện.
- \`skip(n)\` bỏ qua n frame đầu.
- \`limit(n)\` giới hạn số frame được xử lý.
- \`findFirst()\` dừng khi tìm được frame đầu tiên phù hợp.

Stream chỉ hợp lệ trong callback truyền cho \`walk\`. Không lưu stream vào biến để sử dụng sau khi callback kết thúc, cũng không trả stream ra ngoài callback. Hãy trả về giá trị đã được tính trong callback, chẳng hạn tên method, tên class hoặc một object dữ liệu riêng.

## 4. Chọn frame bằng skip và filter

### 4.1. Dùng skip khi cấu trúc lời gọi đã biết

Nếu \`walk\` được gọi trực tiếp trong \`Repository.read()\`, frame đầu tiên là \`Repository.read()\`, frame thứ hai là caller của nó:

~~~java
Class<?> directCaller = WALKER.walk(frames ->
        frames.skip(1)
              .findFirst()
              .map(StackWalker.StackFrame::getDeclaringClass)
              .orElseThrow(IllegalStateException::new));
~~~

Ở đây \`skip(1)\` bỏ frame hiện tại rồi chọn frame kế tiếp. Để chọn caller cao hơn nữa, có thể tăng số frame bỏ qua.

Cách này ngắn gọn khi call chain ổn định. Tuy nhiên, nếu thêm helper, proxy hoặc wrapper, chỉ số frame có thể thay đổi. Không nên dựa vào một con số skip cố định khi cấu trúc stack có thể thay đổi thường xuyên.

### 4.2. Dùng filter khi cần chọn theo quy tắc

Nếu mục tiêu là tìm frame thuộc một class hoặc package nhất định, hãy lọc theo thuộc tính thay vì đoán vị trí:

~~~java
String serviceMethod = WALKER.walk(frames ->
        frames.filter(frame ->
                    frame.getClassName().equals("example.Service"))
              .findFirst()
              .map(StackWalker.StackFrame::getMethodName)
              .orElse("<not found>"));
~~~

Với walker đã bật \`RETAIN_CLASS_REFERENCE\`, có thể lọc theo class thực:

~~~java
Class<?> serviceClass = WALKER.walk(frames ->
        frames.filter(frame ->
                    frame.getDeclaringClass() == Service.class)
              .findFirst()
              .map(StackWalker.StackFrame::getDeclaringClass)
              .orElseThrow(IllegalStateException::new));
~~~

Filter theo class hoặc package thường dễ hiểu và ít phụ thuộc số tầng helper hơn. Hãy xác định rõ frame nội bộ nào cần bỏ qua; một bộ lọc quá rộng có thể chọn nhầm frame hoặc không tìm thấy frame nào.

## 5. Reflection frame và hidden frame

Mặc định, StackWalker không hiển thị reflection frame và hidden frame. Điều này giúp stack dễ đọc hơn trong các trường hợp thông thường.

Khi cần kiểm tra sâu hơn, có thể tạo walker với các option:

~~~java
Set<StackWalker.Option> options = EnumSet.of(
        StackWalker.Option.RETAIN_CLASS_REFERENCE,
        StackWalker.Option.SHOW_REFLECT_FRAMES,
        StackWalker.Option.SHOW_HIDDEN_FRAMES);

StackWalker detailedWalker = StackWalker.getInstance(options);
~~~

- \`SHOW_REFLECT_FRAMES\` yêu cầu hiển thị các frame liên quan đến reflection.
- \`SHOW_HIDDEN_FRAMES\` yêu cầu hiển thị các frame ẩn, chẳng hạn một số frame do runtime hoặc cơ chế thực thi tạo ra.
- \`RETAIN_CLASS_REFERENCE\` cho phép truy cập đối tượng class qua \`getCallerClass()\` và \`getDeclaringClass()\`.

Chỉ bật những option cần thiết. Khi thêm reflection hoặc hidden frame, thứ tự và số lượng frame quan sát được có thể khác, vì vậy các phép \`skip(n)\` viết cho walker mặc định có thể chọn một frame khác.

Các option được cố định khi tạo walker. Nếu cần cả cách nhìn mặc định và cách nhìn chi tiết, tạo hai walker với hai cấu hình riêng.

## 6. StackFrame chứa những thông tin nào?

Một \`StackWalker.StackFrame\` có thể cung cấp:

| Method | Ý nghĩa |
|---|---|
| \`getClassName()\` | Tên class chứa frame |
| \`getMethodName()\` | Tên method |
| \`getDeclaringClass()\` | Đối tượng \`Class<?>\`; cần \`RETAIN_CLASS_REFERENCE\` |
| \`getFileName()\` | Tên file nguồn nếu có |
| \`getLineNumber()\` | Số dòng nếu runtime có thông tin |
| \`isNativeMethod()\` | Frame có phải native method hay không |

Không phải frame nào cũng có file nguồn hoặc số dòng. \`getFileName()\` có thể trả về \`null\`, và \`getLineNumber()\` có thể trả về giá trị âm nếu không có thông tin dòng.

Không nên dùng số dòng hoặc tên file làm định danh ổn định cho method. Chúng phụ thuộc cách biên dịch, debug information và runtime.

## 7. Ví dụ hoàn chỉnh: caller trực tiếp và caller qua helper

Tạo file **CallerFrameDemo.java**:

~~~java
import java.lang.StackWalker;
import java.util.stream.Collectors;

public class CallerFrameDemo {

    private static final StackWalker WALKER =
            StackWalker.getInstance(
                    StackWalker.Option.RETAIN_CLASS_REFERENCE);

    private static final class Client {
        static void start() {
            Service.load();
        }
    }

    private static final class Service {
        static void load() {
            Repository.read();
        }
    }

    private static final class Repository {
        static void read() {
            Class<?> directCaller = WALKER.getCallerClass();
            Class<?> helperImmediateCaller =
                    CallerTools.immediateCaller();
            Class<?> callerAboveRepository =
                    CallerTools.callerAboveRepository();

            String firstFrames = WALKER.walk(frames ->
                    frames.limit(4)
                          .map(StackWalker.StackFrame::getMethodName)
                          .collect(Collectors.joining(" -> ")));

            String serviceMethod = WALKER.walk(frames ->
                    frames.filter(frame ->
                                frame.getDeclaringClass() == Service.class)
                          .findFirst()
                          .map(StackWalker.StackFrame::getMethodName)
                          .orElse("<not found>"));

            System.out.println("direct caller = "
                    + directCaller.getSimpleName());
            System.out.println("helper immediate caller = "
                    + helperImmediateCaller.getSimpleName());
            System.out.println("caller above repository = "
                    + callerAboveRepository.getSimpleName());
            System.out.println("first frames = " + firstFrames);
            System.out.println("filtered service method = "
                    + serviceMethod);
        }
    }

    private static final class CallerTools {
        static Class<?> immediateCaller() {
            return WALKER.getCallerClass();
        }

        static Class<?> callerAboveRepository() {
            return WALKER.walk(frames ->
                    frames.skip(2)
                          .findFirst()
                          .map(StackWalker.StackFrame::getDeclaringClass)
                          .orElseThrow(IllegalStateException::new));
        }
    }

    public static void main(String[] args) {
        Client.start();
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 -Xlint:all -d out CallerFrameDemo.java
java -cp out CallerFrameDemo
~~~

Output chính xác:

~~~text
direct caller = Service
helper immediate caller = Repository
caller above repository = Service
first frames = read -> load -> start -> main
filtered service method = load
~~~

Giải thích:

- \`Repository.read()\` gọi trực tiếp \`getCallerClass()\`, nên nhận class \`Service\`.
- \`CallerTools.immediateCaller()\` gọi \`getCallerClass()\` từ bên trong helper; caller trực tiếp của helper là \`Repository\`.
- \`callerAboveRepository()\` dùng \`walk\` và \`skip(2)\`: bỏ frame helper và frame repository, sau đó chọn \`Service\`.
- \`first frames\` cho thấy thứ tự từ method hiện tại đi ngược lên caller.
- \`filter\` tìm frame thuộc \`Service\` và lấy tên method \`load\`.

Trong code thực tế, thay \`skip(2)\` bằng filter theo class/package nếu số tầng helper không cố định.

## 8. Khi nào nên dùng getCallerClass và khi nào dùng walk?

| Nhu cầu | Cách phù hợp |
|---|---|
| Lấy caller trực tiếp của method hiện tại | \`getCallerClass()\` |
| Chọn frame theo class hoặc package | \`walk(...filter...findFirst())\` |
| Bỏ một số tầng helper đã biết | \`walk(...skip(n)...) \` |
| Lấy nhiều method để ghi log | \`walk(...limit...map...collect())\` |
| Kiểm tra reflection hoặc hidden frame | Walker với option tương ứng |

Ưu tiên \`getCallerClass()\` khi chỉ cần caller trực tiếp. Dùng \`walk\` khi cần chọn frame theo quy tắc, lấy nhiều frame hoặc thu thập metadata.

Giữ callback của \`walk\` ngắn và chỉ lấy thông tin thực sự cần. Stack walking có chi phí; không nên duyệt toàn bộ stack lặp đi lặp lại trong đường xử lý hiệu năng cao nếu một lần lấy caller trực tiếp đã đủ.

## 9. Giới hạn và lưu ý bảo mật

Stack trace mô tả đường gọi tại thời điểm quan sát. Nó không phải một định danh lâu dài của thành phần gọi và không nên được dùng thay cho hợp đồng API rõ ràng.

Không dùng \`getCallerClass()\` để quyết định quyền truy cập hoặc xác thực người dùng. Proxy, reflection, wrapper, method handle và thay đổi cấu trúc ứng dụng có thể làm caller quan sát được khác với thành phần nghiệp vụ mà bạn định nhận diện. Hãy truyền principal, capability hoặc context tường minh cho logic phân quyền.

Tên class và package có thể tiết lộ cấu trúc nội bộ. Tránh đưa toàn bộ stack hoặc thông tin class nhạy cảm vào log công khai hay response gửi cho client.

## 10. Lỗi thường gặp

### Quên RETAIN_CLASS_REFERENCE

\`getCallerClass()\` và \`StackFrame.getDeclaringClass()\` yêu cầu walker có \`RETAIN_CLASS_REFERENCE\`. Nếu không, API ném \`IllegalCallerException\`.

### Nhầm caller với class chứa method hiện tại

\`getCallerClass()\` trả về caller trực tiếp của method đang gọi API. Class chứa method đó có thể khác.

### Bọc getCallerClass trong helper rồi mong nó bỏ qua helper

Caller trực tiếp của helper là nơi gọi helper. Nếu cần frame cao hơn, hãy dùng \`walk\` và quy tắc chọn frame rõ ràng.

### Dùng skip(n) mà không tính frame hiện tại

Frame đầu tiên trong \`walk\` thường là method đang gọi \`walk\`. Hãy tính cả frame này trước khi chọn caller.

### Dùng chỉ số skip cố định trong call chain thay đổi

Thêm wrapper, proxy hoặc reflection có thể làm vị trí frame thay đổi. Filter theo class/package phù hợp hơn khi có thể xác định rõ tiêu chí.

### Giữ Stream sau khi walk kết thúc

Stream chỉ dùng trong callback. Hãy collect hoặc chuyển thành giá trị cần thiết ngay bên trong callback.

### Giả định mọi frame đều có file và số dòng

Runtime có thể không cung cấp debug metadata. Kiểm tra giá trị trả về trước khi hiển thị hoặc sử dụng.

### Dùng caller để phân quyền

Stack là dữ liệu chẩn đoán, không phải identity hoặc authorization context. Dùng thông tin người gọi được truyền tường minh.

## 11. Checklist

- [ ] Đã tạo walker với \`RETAIN_CLASS_REFERENCE\` khi cần Class object.
- [ ] Đã hiểu \`getCallerClass()\` trả về caller trực tiếp của method đang gọi API.
- [ ] Đã kiểm tra helper có làm thay đổi caller quan sát được hay không.
- [ ] Đã xác định frame đầu tiên trước khi dùng \`skip(n)\`.
- [ ] Đã dùng filter theo class/package khi call chain không cố định.
- [ ] Đã bật reflection/hidden frame option chỉ khi cần.
- [ ] Đã xử lý khả năng thiếu file name hoặc line number.
- [ ] Đã giữ toàn bộ thao tác stream bên trong callback \`walk\`.
- [ ] Không dùng stack frame làm cơ chế phân quyền.
- [ ] Đã biên dịch và chạy ví dụ với Java 9+.

## 12. Tài liệu tham khảo

- [Java SE 17 API: StackWalker](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackWalker.html)
- [Java SE 17 API: StackWalker.StackFrame](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackWalker.StackFrame.html)

