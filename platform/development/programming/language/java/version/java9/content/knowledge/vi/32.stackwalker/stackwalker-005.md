# Giữ tham chiếu `Class<?>` trong StackWalker bằng `RETAIN_CLASS_REFERENCE`

`StackWalker` là API được bổ sung trong Java 9 để duyệt các stack frame của thread hiện tại theo cách có kiểm soát. Theo mặc định, một `StackWalker` cung cấp thông tin như tên lớp, tên phương thức và vị trí mã nguồn, nhưng không giữ tham chiếu `Class<?>` trong mỗi frame. Khi cần lấy đối tượng `Class` thực tế từ stack frame hoặc cần dùng `getCallerClass()`, hãy tạo walker với tùy chọn `StackWalker.Option.RETAIN_CLASS_REFERENCE`.

Tùy chọn này hữu ích cho framework, thư viện, công cụ chẩn đoán hoặc logic cần nhận diện chính xác lớp đang gọi. Nó cung cấp class identity thực tế thay vì chỉ một chuỗi tên lớp. Việc giữ tham chiếu lớp cần được dùng có chủ đích vì tham chiếu `Class<?>` cũng liên quan đến class loader đang định nghĩa lớp đó.

## 1. StackWalker và StackFrame

Một stack trace mô tả chuỗi lời gọi phương thức của một thread tại một thời điểm. `StackWalker` cho phép duyệt các frame này bằng API có thể dừng sớm hoặc chỉ trích xuất phần thông tin cần thiết, thay vì luôn tạo toàn bộ stack trace.

Mỗi `StackFrame` mô tả một lời gọi phương thức và cung cấp các thông tin như:

- `getClassName()`: tên đầy đủ của lớp khai báo phương thức.
- `getMethodName()`: tên phương thức.
- `getFileName()`: tên file nguồn nếu thông tin có sẵn.
- `getLineNumber()`: số dòng nếu thông tin có sẵn.
- `isNativeMethod()`: cho biết frame có thuộc phương thức native hay không.
- `getDeclaringClass()`: đối tượng `Class<?>` của lớp khai báo frame; cần bật `RETAIN_CLASS_REFERENCE`.

StackWalker chỉ duyệt stack của thread đang thực hiện lời gọi. Nó không đọc stack của một thread tùy ý khác, cũng không cung cấp biến local, giá trị tham số hoặc trạng thái heap của phương thức.

## 2. Vì sao mặc định không giữ Class reference?

Walker mặc định được tạo bằng `StackWalker.getInstance()` không bật `RETAIN_CLASS_REFERENCE`. Bạn vẫn có thể đọc tên lớp qua `StackFrame.getClassName()`, nhưng không thể lấy đối tượng `Class<?>` từ frame.

```java
StackWalker walker = StackWalker.getInstance();

walker.walk(frames -> frames
        .findFirst()
        .map(StackWalker.StackFrame::getClassName)
        .orElse("unknown"));
```

Với walker mặc định, gọi `StackFrame.getDeclaringClass()` ném `UnsupportedOperationException`. Gọi `StackWalker.getCallerClass()` cũng ném `UnsupportedOperationException`, vì cả hai thao tác đều cần class reference được giữ lại.

Việc chỉ cung cấp tên lớp theo mặc định giúp tránh giữ tham chiếu lớp không cần thiết trong quá trình duyệt stack. Nếu ứng dụng chỉ cần ghi log hoặc hiển thị tên lớp/phương thức, không cần bật tùy chọn này.

## 3. Bật `RETAIN_CLASS_REFERENCE`

Tạo walker với tùy chọn:

```java
StackWalker walker = StackWalker.getInstance(
        StackWalker.Option.RETAIN_CLASS_REFERENCE
);
```

Hoặc khi cần nhiều tùy chọn, truyền một `Set<StackWalker.Option>`:

```java
Set<StackWalker.Option> options = EnumSet.of(
        StackWalker.Option.RETAIN_CLASS_REFERENCE
);
StackWalker walker = StackWalker.getInstance(options);
```

Sau khi bật tùy chọn, `StackFrame.getDeclaringClass()` trả về `Class<?>` tương ứng với frame:

```java
Class<?> declaringClass = walker.walk(frames ->
        frames.findFirst()
                .map(StackWalker.StackFrame::getDeclaringClass)
                .orElseThrow(() -> new IllegalStateException("No stack frame"))
);
```

Đối tượng `Class<?>` này có thể dùng cho các thao tác cần class identity, ví dụ so sánh lớp bằng `==`, lấy class loader hoặc truy cập metadata được phép qua Reflection. `RETAIN_CLASS_REFERENCE` không tự cấp quyền truy cập private member, không bỏ qua kiểm tra truy cập của Java và không biến stack inspection thành cơ chế phân quyền.

## 4. Dùng `getCallerClass()`

`StackWalker.getCallerClass()` trả về lớp của caller trực tiếp của phương thức hiện tại. Nó thường hữu ích khi một API cần biết lớp nào đã gọi vào một phương thức thư viện.

```java
private static final StackWalker WALKER =
        StackWalker.getInstance(StackWalker.Option.RETAIN_CLASS_REFERENCE);

static Class<?> callerClass() {
    return WALKER.getCallerClass();
}
```

Nếu `callerClass()` được gọi từ `Service.execute()`, kết quả là lớp khai báo `Service.execute()` gọi `callerClass()`. Nói cách khác, `getCallerClass()` nhìn qua chính phương thức gọi nó để trả về caller của phương thức đó. Khi bọc lời gọi trong helper, hãy nhớ rằng caller được xác định theo vị trí gọi thực tế; helper có thể làm thay đổi lớp mà API trả về so với điều bạn mong đợi.

`getCallerClass()` yêu cầu walker có `RETAIN_CLASS_REFERENCE`. Nếu dùng walker mặc định, phương thức ném `UnsupportedOperationException`. Nếu không thể xác định caller theo hợp đồng API, phương thức có thể ném `IllegalCallerException`; vì vậy không nên gọi nó từ một ngữ cảnh mà caller frame không được bảo đảm.

## 5. Duyệt stack bằng `walk()`

`walk(Function<Stream<StackFrame>, T>)` đưa một stream các frame cho hàm xử lý và trả về kết quả do hàm đó tạo ra. Frame đầu tiên là frame của phương thức gọi `walk()`, tiếp theo là caller của nó.

Ví dụ lấy lớp khai báo frame hiện tại:

```java
Class<?> currentFrameClass = WALKER.walk(frames ->
        frames.findFirst()
                .map(StackWalker.StackFrame::getDeclaringClass)
                .orElseThrow(() -> new IllegalStateException("Empty stack"))
);
```

Ví dụ lấy tối đa ba frame và chuyển thành chuỗi dễ ghi log:

```java
List<String> frames = WALKER.walk(stream -> stream
        .limit(3)
        .map(frame -> frame.getDeclaringClass().getName()
                + "#" + frame.getMethodName())
        .collect(Collectors.toList()));
```

Stream do `walk()` cung cấp chỉ có hiệu lực trong hàm callback. Stream được đóng khi callback trả về; không lưu stream để duyệt sau hoặc trả trực tiếp stream ra ngoài. Nếu cần giữ kết quả, hãy materialize thành dữ liệu độc lập như `List<String>`, tên lớp hoặc một vài đối tượng `Class<?>` có chủ đích.

Ưu tiên `limit()`, `findFirst()` hoặc các thao tác ngắn mạch khác khi chỉ cần một phần stack. Duyệt toàn bộ stack khi không cần thiết có thể tạo thêm công việc và giữ các tham chiếu lâu hơn.

## 6. Khác biệt giữa tên lớp và Class identity

`getClassName()` trả về một chuỗi. Hai lớp được định nghĩa bởi hai class loader khác nhau có thể có cùng tên đầy đủ, nhưng vẫn là hai kiểu khác nhau trong JVM. Khi logic cần phân biệt class identity thực sự, so sánh `Class<?>` là chính xác hơn:

```java
if (frame.getDeclaringClass() == ExpectedService.class) {
    // Frame thuộc đúng Class object ExpectedService.
}
```

Không nên thay so sánh class identity bằng `getClassName().equals(...)` nếu ứng dụng có plugin, application server, module loader hoặc nhiều class loader. Tên giống nhau không đảm bảo hai lớp là cùng một kiểu runtime.

Ngược lại, nếu chỉ hiển thị log hoặc xuất dữ liệu chẩn đoán, tên lớp thường đủ dùng và ít ràng buộc vòng đời class loader hơn. Chỉ bật `RETAIN_CLASS_REFERENCE` khi thực sự cần đối tượng `Class<?>`.

## 7. Vòng đời Class và class loader

Đối tượng `Class<?>` gắn với lớp đã được một class loader định nghĩa. Khi ứng dụng giữ một tham chiếu mạnh đến `Class<?>`, nó cũng có thể gián tiếp giữ class loader và các lớp được loader quản lý còn sống lâu hơn dự kiến.

Do đó:

- Không lưu vô thời hạn các `Class<?>` lấy từ stack nếu chỉ cần tên lớp để log.
- Tránh đưa class reference vào cache toàn cục mà không có chính sách xóa phù hợp.
- Với hệ thống plugin hoặc hot reload, chú ý tham chiếu từ singleton, listener, thread-local hoặc cache có thể giữ class loader cũ.
- Chỉ giữ class reference trong phạm vi cần thiết; nếu cần cache, thiết kế vòng đời cache phù hợp với vòng đời module/class loader.

`RETAIN_CLASS_REFERENCE` không tự gây rò rỉ bộ nhớ. Rủi ro phát sinh khi ứng dụng lưu và giữ các tham chiếu đó lâu hơn vòng đời dự kiến. Dùng tùy chọn này có chủ đích và chỉ materialize những kết quả thật sự cần.

## 8. Không dùng StackWalker làm ranh giới bảo mật

Stack inspection có thể hỗ trợ framework nhận diện caller, thêm thông tin chẩn đoán hoặc điều chỉnh hành vi theo ngữ cảnh. Tuy nhiên, không nên xem tên lớp hay caller class là bằng chứng xác thực danh tính hoặc quyền của người dùng.

Stack có thể thay đổi khi thêm wrapper, proxy, reflection, callback hoặc refactor mã nguồn. Các lớp ẩn và frame nội bộ cũng có thể ảnh hưởng cách quan sát tùy cấu hình walker. Nếu một quyết định bảo mật phụ thuộc vào caller, hãy thiết kế API và quyền truy cập tường minh; không dựa duy nhất vào vị trí frame trong stack.

Không dùng `StackWalker` để thay thế xác thực, authorization, kiểm tra quyền hệ điều hành hoặc kiểm soát truy cập dữ liệu. Nó chỉ cung cấp thông tin về call stack của thread hiện tại.

## 9. Ví dụ hoàn chỉnh: giữ Class reference và lấy caller

Chương trình dưới đây so sánh walker mặc định với walker bật `RETAIN_CLASS_REFERENCE`. Một lớp lồng `Service` gọi API; chương trình in caller class, lớp của frame hiện tại và hai frame đầu. Sau đó nó xác nhận walker mặc định không hỗ trợ `getDeclaringClass()` và `getCallerClass()`.

Tạo tệp `RetainClassReferenceDemo.java`:

```java
public class RetainClassReferenceDemo {
    private static final StackWalker RETAINING =
            StackWalker.getInstance(StackWalker.Option.RETAIN_CLASS_REFERENCE);
    private static final StackWalker NAME_ONLY = StackWalker.getInstance();

    private static final class Service {
        void execute() {
            Class<?> caller = RETAINING.getCallerClass();
            Class<?> currentFrameClass = RETAINING.walk(frames ->
                    frames.findFirst().get().getDeclaringClass());
            String frameName = RETAINING.walk(frames ->
                    frames.limit(2)
                            .map(frame -> frame.getDeclaringClass().getSimpleName()
                                    + "#" + frame.getMethodName())
                            .reduce((first, second) -> first + " -> " + second)
                            .get());

            System.out.println("Caller class: " + caller.getSimpleName());
            System.out.println("Current frame class: " + currentFrameClass.getSimpleName());
            System.out.println("Top frames: " + frameName);

            try {
                NAME_ONLY.walk(frames ->
                        frames.findFirst().get().getDeclaringClass());
            } catch (UnsupportedOperationException ex) {
                System.out.println("Default walker retains Class: false");
            }

            try {
                NAME_ONLY.getCallerClass();
            } catch (UnsupportedOperationException ex) {
                System.out.println("Default walker supports getCallerClass: false");
            }
        }
    }

    public static void main(String[] args) {
        new Service().execute();
    }
}
```

Biên dịch và chạy bằng JDK 9 trở lên:

```bash
javac --release 9 -Xlint:all RetainClassReferenceDemo.java
java RetainClassReferenceDemo
```

Kết quả stdout:

```text
Caller class: RetainClassReferenceDemo
Current frame class: Service
Top frames: Service#execute -> RetainClassReferenceDemo#main
Default walker retains Class: false
Default walker supports getCallerClass: false
```

Kết quả cho thấy `getCallerClass()` trong `Service.execute()` trả về lớp đã gọi `execute()`, tức `RetainClassReferenceDemo`. Ngược lại, frame đầu tiên của lời gọi `walk()` nằm trong `Service.execute()`, vì vậy `getDeclaringClass()` của frame đó là `Service`.

## 10. Khi nào nên bật `RETAIN_CLASS_REFERENCE`?

**Nên bật khi:**

- Framework cần xác định chính xác lớp gọi một API.
- Công cụ phân tích stack cần đối chiếu frame với `Class<?>` đã biết.
- Cần phân biệt hai lớp cùng tên nhưng do class loader khác nhau định nghĩa.
- Logic cần metadata hoặc class loader của lớp khai báo frame.

**Không cần bật khi:**

- Chỉ ghi tên lớp và tên phương thức vào log.
- Chỉ cần số dòng hoặc tên file nguồn.
- Stack chỉ được hiển thị cho người dùng hoặc hệ thống giám sát.
- Không có thao tác nào cần class identity.

## 11. Lỗi thường gặp

- **Dùng walker mặc định rồi gọi `getDeclaringClass()`:** sẽ nhận `UnsupportedOperationException`; tạo walker với `RETAIN_CLASS_REFERENCE`.
- **Gọi `getCallerClass()` trên walker không giữ class reference:** thao tác này cũng ném `UnsupportedOperationException`.
- **Nhầm frame đầu tiên với caller class:** frame đầu tiên trong `walk()` là phương thức gọi `walk()`; `getCallerClass()` trả về caller của phương thức đang gọi nó.
- **Bọc `getCallerClass()` trong helper mà không xét call site:** caller được xác định theo vị trí gọi helper, nên kết quả có thể khác mong muốn.
- **Giữ stream từ `walk()` để dùng sau:** stream chỉ có hiệu lực trong callback; hãy trích xuất kết quả trước khi callback kết thúc.
- **So sánh tên lớp thay cho class identity:** hai class loader có thể định nghĩa hai lớp cùng tên nhưng khác `Class<?>`.
- **Giữ Class reference trong cache toàn cục:** có thể kéo dài vòng đời class loader; chỉ giữ khi cần và quản lý vòng đời tham chiếu.
- **Dùng stack frame làm cơ chế authorization:** call stack là dữ liệu chẩn đoán/runtime, không thay thế thiết kế quyền truy cập tường minh.

`StackWalker.Option.RETAIN_CLASS_REFERENCE` mở rộng stack inspection để lấy `Class<?>` từ frame và dùng `getCallerClass()`. Hãy bật tùy chọn khi thật sự cần class identity; nếu chỉ cần thông tin văn bản để chẩn đoán, walker mặc định nhẹ và phù hợp hơn.