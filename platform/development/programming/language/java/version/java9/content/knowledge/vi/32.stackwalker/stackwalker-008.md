# Chia sẻ StackWalker giữa các luồng

## Mục tiêu

`StackWalker` được giới thiệu trong Java 9 để duyệt call stack của thread hiện tại một cách có kiểm soát. API này hỗ trợ lọc frame, giới hạn số frame cần đọc và truy cập trực tiếp `Class<?>` khi bật tùy chọn phù hợp.

Một `StackWalker` có thể được chia sẻ và sử dụng đồng thời từ nhiều thread vì các instance của lớp này là thread-safe. Tuy nhiên, mỗi lần gọi `walk(...)` chỉ quan sát stack của **thread đang thực hiện lời gọi đó**. Chia sẻ đối tượng walker không biến nó thành công cụ đọc stack của mọi thread từ một thread trung tâm.

Điểm cần ghi nhớ:

- Có thể tạo một instance dùng chung, thường là `static final`.
- Mỗi thread gọi `walk` sẽ duyệt stack của chính thread đó.
- Không cần `synchronized` chỉ để bảo vệ việc gọi chung StackWalker.
- Stream frame phải được tiêu thụ trong callback truyền cho `walk`; không lưu stream để dùng sau.
- Nếu cần kiểm tra stack của một worker, hãy chạy thao tác thu thập stack ngay bên trong worker đó.

## 1. StackWalker là gì?

`StackWalker` thuộc gói `java.lang` và có từ Java 9. Nó cung cấp cách duyệt các stack frame của thread đang gọi API mà không cần tạo toàn bộ `Throwable` chỉ để lấy stack trace.

Tạo walker mặc định:

~~~java
StackWalker walker = StackWalker.getInstance();
~~~

Duyệt các frame:

~~~java
walker.forEach(frame ->
        System.out.println(frame.getClassName()
                + "#" + frame.getMethodName())
);
~~~

Hoặc dùng `walk(Function)` để lọc và biến đổi stack thành kết quả:

~~~java
List<String> frames = walker.walk(stream ->
        stream.limit(5)
                .map(frame -> frame.getClassName()
                        + "#" + frame.getMethodName())
                .collect(Collectors.toList())
);
~~~

`walk` phù hợp khi cần xử lý một phần stack, trả về danh sách thông tin hoặc tìm frame thỏa điều kiện. Stream được quản lý trong phạm vi lời gọi walk; callback cần thực hiện thao tác terminal trước khi trả về.

## 2. Vì sao có thể chia sẻ một StackWalker?

API quy định các instance `StackWalker` là thread-safe. Cấu hình của walker được thiết lập khi tạo instance và không thay đổi trong quá trình sử dụng. Vì vậy, nhiều thread có thể đồng thời gọi `walk`, `forEach` hoặc các thao tác đọc caller trên cùng một instance.

Một cách khai báo thường dùng:

~~~java
private static final StackWalker WALKER =
        StackWalker.getInstance(StackWalker.Option.RETAIN_CLASS_REFERENCE);
~~~

Mỗi lần gọi walker sẽ thực hiện một lần duyệt stack theo ngữ cảnh thread hiện tại. Không có một bộ đếm position hoặc iterator dùng chung khiến các thread làm lệch kết quả của nhau.

Không cần tạo một walker mới cho mỗi task chỉ vì task chạy trên thread khác. Tạo riêng instance chỉ hợp lý khi cần cấu hình option khác nhau hoặc muốn quản lý một cấu hình riêng cho từng thành phần.

## 3. Stack được đọc là stack của thread gọi walk

Đây là điểm dễ hiểu nhầm nhất khi dùng StackWalker trong chương trình đa luồng.

Giả sử thread main gửi một task cho ExecutorService:

~~~java
executor.submit(() -> inspectCurrentStack());
~~~

Nếu `inspectCurrentStack()` gọi `WALKER.walk(...)`, các frame nhận được thuộc về thread pool đang thực thi task. Chúng không phải stack của thread main đã submit task.

Ngược lại, nếu main gọi `WALKER.walk(...)` sau khi submit, walker chỉ nhìn thấy stack của main tại thời điểm đó. Nó không tự chuyển sang thread worker.

Do đó:

- Muốn ghi nhận stack của task: gọi StackWalker bên trong task.
- Muốn ghi nhận stack của callback: gọi StackWalker bên trong callback.
- Muốn ghi nhận stack của request đang được xử lý: gọi trong thread xử lý request tại thời điểm cần quan sát.
- Không dùng StackWalker như API để truyền một thread ID rồi đọc stack của thread khác.

Nếu cần chẩn đoán thread khác từ một thread quản trị, hãy xem các API quản lý thread như `ThreadMXBean` trong `java.lang.management`. Đó là mục đích khác với việc chia sẻ StackWalker.

## 4. Cấu hình StackWalker bằng Option

`StackWalker.getInstance(...)` cho phép chọn những loại frame và thông tin được giữ lại.

| Option | Ý nghĩa |
|---|---|
| Mặc định, không bật option | Bỏ qua reflection frame và hidden frame trong kết quả thông thường |
| `SHOW_REFLECT_FRAMES` | Bao gồm frame do reflection tạo ra |
| `SHOW_HIDDEN_FRAMES` | Bao gồm hidden frame như một số frame do runtime hoặc lambda implementation tạo ra |
| `RETAIN_CLASS_REFERENCE` | Cho phép lấy đối tượng `Class<?>` từ StackFrame và dùng `getCallerClass()` |

Ví dụ bật class reference:

~~~java
StackWalker walker = StackWalker.getInstance(
        StackWalker.Option.RETAIN_CLASS_REFERENCE
);
~~~

Khi bật option này, có thể gọi:

~~~java
Class<?> declaringClass = walker.walk(stream ->
        stream.findFirst()
                .map(StackWalker.StackFrame::getDeclaringClass)
                .orElse(Object.class)
);
~~~

Nếu không bật `RETAIN_CLASS_REFERENCE`, gọi `StackFrame.getDeclaringClass()` sẽ ném `UnsupportedOperationException`. Nếu chỉ cần tên lớp, có thể dùng `getClassName()` mà không cần giữ Class reference.

Có thể kết hợp nhiều option bằng một Set:

~~~java
Set<StackWalker.Option> options = EnumSet.of(
        StackWalker.Option.RETAIN_CLASS_REFERENCE,
        StackWalker.Option.SHOW_REFLECT_FRAMES
);

StackWalker walker = StackWalker.getInstance(options);
~~~

Chỉ bật những option thực sự cần thiết. Hiển thị thêm hidden hoặc reflection frame có thể làm stack dài và khó đọc hơn.

## 5. Dùng walk đúng phạm vi và thời gian sống của Stream

`walk(Function)` cung cấp một Stream các StackFrame để callback xử lý. Stream này được đóng khi callback kết thúc. Vì vậy, không trả stream ra ngoài hoặc lưu nó vào field để dùng ở thread khác.

Không nên viết:

~~~java
Stream<StackWalker.StackFrame> saved = walker.walk(stream -> stream);
~~~

Stream đã hết thời gian sử dụng sau khi callback trả về. Thay vào đó, hãy chuyển frame thành dữ liệu cần giữ ngay trong callback:

~~~java
List<String> snapshot = walker.walk(stream ->
        stream.limit(10)
                .map(frame -> frame.getClassName()
                        + "#" + frame.getMethodName())
                .collect(Collectors.toList())
);
~~~

Danh sách String có thể được trả về, ghi log hoặc gửi sang thread khác. Cách này giữ lại thông tin cần thiết mà không giữ stream sống ngắn hoặc phụ thuộc vào lần duyệt stack đã kết thúc.

Nếu cần giữ class reference, có thể chuyển frame thành `Class<?>` trong callback khi walker được tạo với `RETAIN_CLASS_REFERENCE`. Chỉ giữ dữ liệu thực sự cần cho chẩn đoán để tránh giữ tham chiếu không cần thiết.

## 6. Chia sẻ StackWalker và dữ liệu ứng dụng là hai vấn đề khác nhau

Thread-safe của StackWalker chỉ đảm bảo việc sử dụng chính instance walker có thể diễn ra đồng thời. Nó không tự bảo vệ dữ liệu do ứng dụng ghi nhận trong callback.

Ví dụ, nếu nhiều thread cùng ghi kết quả vào một `ArrayList` dùng chung, vẫn cần đồng bộ hoặc dùng collection phù hợp với concurrency. Tương tự, logger, cache hoặc bộ đếm tùy chỉnh cần tuân theo quy tắc thread-safety riêng.

Mẫu tốt là để mỗi task tạo kết quả cục bộ rồi trả về:

~~~java
Future<List<String>> result = executor.submit(
        () -> captureCurrentStack()
);
~~~

Sau đó thread điều phối lấy kết quả bằng Future. Nếu cần gom kết quả từ nhiều task, dùng collection thread-safe hoặc tổng hợp sau khi các Future hoàn tất.

Không thêm `synchronized` quanh toàn bộ `WALKER.walk(...)` nếu không có trạng thái dùng chung khác cần bảo vệ. Khóa như vậy chỉ làm các lần đọc stack phải xếp hàng và giảm khả năng chạy song song.

## 7. Giới hạn số frame và chi phí thu thập

Duyệt stack có chi phí. Nếu chỉ cần vị trí gọi gần nhất, không cần thu thập toàn bộ stack.

Dùng `limit(n)` để dừng sớm:

~~~java
List<String> topFrames = WALKER.walk(stream ->
        stream.limit(4)
                .map(frame -> frame.getClassName()
                        + "#" + frame.getMethodName())
                .collect(Collectors.toList())
);
~~~

Một số thực hành hữu ích:

- Chỉ lấy số frame đủ cho mục đích log hoặc tracing.
- Lọc các frame thuộc package nội bộ nếu cần hiển thị stack gọn.
- Tránh gọi stack walking trong vòng lặp nóng nếu không cần.
- Không chuyển mọi frame thành StackTraceElement hoặc String nếu chỉ cần tên method đầu tiên.
- Chọn option tối thiểu để giảm lượng frame cần xử lý.

Overload `getInstance(options, estimatedDepth)` cho phép cung cấp độ sâu dự kiến như một gợi ý tối ưu bộ nhớ. Đây là ước lượng, không phải giới hạn số frame; muốn giới hạn kết quả vẫn phải dùng `limit(n)`.

## 8. Ví dụ hoàn chỉnh: một StackWalker dùng chung trong ExecutorService

Tệp `StackWalkerSharingDemo.java`:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class StackWalkerSharingDemo {
    private static final StackWalker WALKER =
            StackWalker.getInstance(StackWalker.Option.RETAIN_CLASS_REFERENCE);

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);

        try {
            List<Callable<String>> tasks = Arrays.asList(
                    () -> inspect("task-A"),
                    () -> inspect("task-B"),
                    () -> inspect("task-C"),
                    () -> inspect("task-D")
            );

            List<Future<String>> results = executor.invokeAll(tasks);
            for (Future<String> result : results) {
                System.out.println(result.get());
            }
        } finally {
            executor.shutdown();
        }
    }

    private static String inspect(String taskName) {
        String topFrame = WALKER.walk(frames ->
                frames.findFirst()
                        .map(frame -> frame.getDeclaringClass().getSimpleName()
                                + "." + frame.getMethodName())
                        .orElse("<empty>")
        );

        return taskName + " on " + Thread.currentThread().getName()
                + " top=" + topFrame;
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 -Xlint:all StackWalkerSharingDemo.java
java StackWalkerSharingDemo
~~~

Một lần chạy mẫu:

~~~text
task-A on pool-1-thread-1 top=StackWalkerSharingDemo.inspect
task-B on pool-1-thread-2 top=StackWalkerSharingDemo.inspect
task-C on pool-1-thread-2 top=StackWalkerSharingDemo.inspect
task-D on pool-1-thread-1 top=StackWalkerSharingDemo.inspect
~~~

Tên thread được ExecutorService phân công có thể thay đổi giữa các lần chạy. Điều cần quan sát là cả bốn task dùng cùng một instance `WALKER`, nhưng mỗi kết quả ghi nhận thread đang thực thi task và frame đầu tiên là `StackWalkerSharingDemo.inspect`.

Task C và D có thể chạy trên cùng thread đã chạy task A hoặc B vì thread pool tái sử dụng worker. StackWalker vẫn đọc stack hiện tại tại từng lần gọi, không giữ stack của task trước.

## 9. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Tạo một StackWalker mới cho mỗi task mà không có lý do | Hiểu nhầm instance không thread-safe | Chia sẻ một instance đã cấu hình nếu các task cần cùng option |
| Nghĩ walker dùng chung đọc được stack của mọi thread | Nhầm thread-safety với khả năng inspect thread khác | Gọi walk bên trong thread cần thu thập stack |
| Lưu Stream<StackFrame> để xử lý sau | Stream bị đóng khi callback walk kết thúc | Chuyển frame thành String hoặc dữ liệu cần thiết ngay trong callback |
| Gọi getDeclaringClass() khi chưa bật option | Class reference không được giữ theo cấu hình mặc định | Tạo walker với RETAIN_CLASS_REFERENCE |
| Bật mọi option mặc định | Stack có thể chứa nhiều frame nội bộ khó đọc | Chỉ bật SHOW_REFLECT_FRAMES/SHOW_HIDDEN_FRAMES khi cần |
| Đồng bộ mọi lần gọi walk | Tạo tranh chấp không cần thiết | Chỉ đồng bộ dữ liệu ứng dụng thực sự dùng chung |
| Giữ toàn bộ stack cho một log ngắn | Tốn chi phí và làm log nhiễu | Dùng limit và filter |
| Cho rằng tên thread trong pool gắn cố định với một task | Executor tái sử dụng worker | Ghi task ID cùng thread name khi cần đối chiếu |

## 10. Checklist triển khai

- Tạo một StackWalker dùng chung nếu nhiều thread cần cùng cấu hình.
- Có thể khai báo instance là `static final`.
- Nhớ rằng StackWalker thread-safe; không khóa chỉ để bảo vệ instance.
- Gọi `walk` bên trong thread mà stack cần được quan sát.
- Không nhầm việc chia sẻ walker với việc đọc stack của thread khác.
- Tiêu thụ Stream trong callback `walk` và chỉ trả dữ liệu đã chuyển đổi.
- Bật `RETAIN_CLASS_REFERENCE` khi cần `getDeclaringClass()` hoặc `getCallerClass()`.
- Chỉ bật hidden/reflection frame khi chẩn đoán yêu cầu.
- Giới hạn số frame và tránh stack walking quá thường xuyên.
- Tự bảo vệ collection hoặc trạng thái dùng chung do callback cập nhật.
- Nếu cần inspect thread khác từ bên ngoài, dùng công cụ quản lý thread phù hợp.

`StackWalker` có thể được chia sẻ an toàn giữa nhiều thread, nhưng mỗi lần duyệt luôn gắn với thread gọi nó. Dùng một instance cấu hình ổn định, gọi `walk` ngay trong task cần quan sát và chuyển frame thành dữ liệu ngay trong callback là cách đơn giản để tận dụng API này trong ứng dụng đa luồng.