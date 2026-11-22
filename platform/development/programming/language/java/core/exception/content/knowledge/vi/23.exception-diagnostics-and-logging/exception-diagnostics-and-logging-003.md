# Tìm frame thuộc mã ứng dụng và đối chiếu dòng nguồn

## 1. Mục tiêu: đi từ stack trace đến đúng câu lệnh trong mã Java

Khi Java ném một exception, thông tin hữu ích nhất thường không phải chỉ là thông báo lỗi mà là **stack trace**: danh sách các vị trí thực thi (*stack frames*) gắn với exception. Mỗi frame có thể chỉ ra lớp, phương thức, tên file nguồn và số dòng. Nhiệm vụ chẩn đoán là **tìm frame liên quan đến mã ứng dụng**, mở đúng phiên bản mã đã chạy, rồi đối chiếu dòng đó với ngữ cảnh và nguyên nhân thực sự.

Ví dụ một trace rút gọn:

~~~text
java.lang.IllegalArgumentException: quantity must be positive
    at com.acme.orders.QuantityValidator.check(QuantityValidator.java:18)
    at com.acme.orders.OrderService.create(OrderService.java:47)
    at com.acme.orders.OrderController.submit(OrderController.java:29)
    at java.base/java.lang.Thread.run(Thread.java:840)
~~~

Đây là **trace minh họa**, không phải output của chương trình runnable ở phần sau. Giả sử các lớp `com.acme.orders.*` thuộc chính ứng dụng đang điều tra:

- Dòng `QuantityValidator.java:18` là điểm đầu của trace, thường gần lệnh ném exception nhất.
- `OrderService.java:47` là call site gọi validator; nó giúp hiểu đầu vào sai từ đâu.
- `OrderController.java:29` là điểm đi vào nghiệp vụ qua lớp controller.
- Frame trong `java.base` thuộc thư viện nền tảng; thường chỉ là phần khung thực thi.

Không phải lúc nào “frame ứng dụng đầu tiên” cũng là nơi **cần sửa**. Nếu lỗi xảy ra trong một thư viện vì ứng dụng cung cấp tham số sai, frame thư viện có thể ở đầu, còn frame ứng dụng đầu tiên chính là call site truyền tham số cần được kiểm tra. Ngược lại, nếu exception bị bọc qua nhiều tầng, trace ở ngoài chỉ cho thấy vị trí bọc; muốn tìm lỗi gốc phải đọc `Caused by` và trace riêng của từng cause.

Bài học này tập trung vào một quy trình thực hành: **đọc cấu trúc frame → phân biệt mã ứng dụng với framework → đi theo chuỗi cause/suppressed → đối chiếu đúng class/file/line với artifact đã triển khai → kiểm chứng giả thuyết bằng ngữ cảnh và tái hiện**.

## 2. Một stack frame chứa những gì?

Dạng hiển thị quen thuộc là:

~~~text
at package.Class.method(FileName.java:123)
~~~

Các thành phần:

| Thành phần | Cách hiểu | Câu hỏi cần hỏi |
| --- | --- | --- |
| `package.Class` | Tên nhị phân của lớp chứa frame | Lớp thuộc module/package ứng dụng, thư viện hay JDK? |
| `method` | Tên phương thức đang thực thi; có thể là `<init>`, `<clinit>` hoặc tên tổng hợp | Đây là constructor, static initialization, lambda hay phương thức bình thường? |
| `FileName.java` | Tên file nguồn gắn với class khi biên dịch, nếu có metadata | File này ở phiên bản source nào? |
| `123` | Số dòng tương ứng với vị trí code theo thông tin debug của class | Dòng đó là lệnh ném lỗi hay lệnh gọi hàm? |
| `at` và phần đầu frame | Quy ước định dạng khi in stack trace | Có module/class loader hoặc thông tin khác ở trước tên class không? |

Từ Java 9, trace có thể hiển thị tiền tố module hoặc class loader, ví dụ:

~~~text
at java.base/java.util.Objects.requireNonNull(Objects.java:209)
at my.module/com.example.app.PaymentService.pay(PaymentService.java:41)
~~~

Các số dòng ở đây **chỉ minh họa**, không phải lời khẳng định về số dòng của mọi phiên bản JDK. `java.base/` là tên module, không phải tên package. Để phân loại frame, cần nhìn vào tên class/package thực sự thay vì cắt chuỗi từ `at` theo một định dạng cố định.

### 2.1. Tên và số dòng có thể không hiện ra

Một số cách hiển thị:

~~~text
at com.example.app.Job.run(Job.java:57)
at com.example.app.GeneratedProxy.invoke(Unknown Source)
at java.base/java.lang.Object.wait(Native Method)
~~~

`Unknown Source` thường nghĩa là không có thông tin file/line đủ dùng cho frame đó. `Native Method` chỉ một phương thức native. Tùy class file và Java runtime, tên file vẫn có thể hiện mà số dòng không có, hoặc cả hai đều vắng.

**Không suy ra rằng chương trình không chạy mã ứng dụng** chỉ vì trace không in số dòng. Hãy kiểm tra class file thực đang chạy, tùy chọn biên dịch, cách sinh bytecode và thông tin debug.

## 3. Thứ tự frame: nơi bắt đầu điều tra và chuỗi lời gọi

Một trace của `Throwable` thường được in theo thứ tự **trên cùng là frame gần vị trí thu thập stack nhất**, tiếp theo là các caller theo hướng đi ngược call stack. Với exception được tạo và ném tại cùng vị trí thông thường, frame đầu thường chỉ đến dòng `throw` hoặc lệnh tạo exception.

Sơ đồ:

~~~text
HTTP endpoint()
    -> OrderService.create()
        -> Validator.check()
            -> throw IllegalArgumentException

Trace khi ném:
    Validator.check(Validator.java:18)          <-- gần điểm ném
    OrderService.create(OrderService.java:47)   <-- chỗ gọi validator
    OrderController.endpoint(Controller.java:29)
    ... framework / thread entry ...
~~~

Những điểm cần nhớ:

1. **Trên cùng không có nghĩa luôn là nguyên nhân cuối cùng**: exception có thể là wrapper như `CompletionException`, `ExecutionException` hoặc `InvocationTargetException`.
2. **Frame ứng dụng đầu tiên không luôn là lỗi lập trình của frame đó**: nó có thể chỉ nhận dữ liệu lỗi từ tầng khác; kiểm tra invariant và đầu vào tại các caller.
3. **Frame của `catch` không nhất thiết là nơi exception bắt đầu**: nếu code chỉ `catch (Exception e) { log(e); }`, trace của `e` vẫn mô tả đường đi đã được ghi lại, không biến thành trace mới tại chỗ log.
4. **Đừng chỉ xem frame cuối hoặc exception cuối cùng được in**: ở một trace nhiều lớp, phần `Caused by` có trace riêng, thường gần nơi lỗi sâu nhất.

### 3.1. Exception được tạo khác thời điểm nó được ném

Stack trace gắn với trạng thái của `Throwable` khi thông tin stack được lấy (thông thường vào lúc đối tượng Throwable được tạo). Ví dụ:

~~~java
IllegalStateException error =
        new IllegalStateException("delayed failure");

doSomethingElse();

throw error;
~~~

Đây là **fragment minh họa**, `doSomethingElse` giả định đã được khai báo. Exception được tạo trước rồi ném sau; trace có thể chỉ tới **dòng tạo đối tượng** thay vì đúng dòng `throw error`. Gọi lại `fillInStackTrace()` có thể thay đổi thông tin stack, nhưng không nên dùng điều đó chỉ để khiến log “đẹp”; nó làm thay đổi nguồn chứng cứ. Một exception cũng có thể được tạo bằng constructor không bật writable stack trace hoặc bị can thiệp `setStackTrace()`, khiến trace không phản ánh đường thực thi thường thấy.

Vì thế đừng khẳng định “line 12 chắc chắn chính là câu lệnh throw” khi bằng chứng chỉ là một StackTraceElement. Hãy đọc code quanh dòng và hiểu thời điểm tạo/ném exception.

## 4. Quy trình bảy bước tìm đúng frame ứng dụng

Khi một log stack trace xuất hiện trong production, có thể làm theo trình tự sau:

1. **Giữ toàn bộ sự kiện:** tên exception, message, stack trace đầy đủ, `Caused by`, `Suppressed`, timestamp, request ID/correlation ID, deployment/build ID và thread name.
2. **Xác định exception ngoài cùng và cause gốc:** wrapper xuất phát từ async/framework hay lỗi thực ở tầng sâu? Đọc từng khối trace thay vì chỉ nhìn dòng đầu.
3. **Khoanh package/module ứng dụng:** dựa trên namespace thực, ví dụ `com.example.billing`, `vn.company.report`, hoặc module ứng dụng đã biết; không chỉ tìm chuỗi tên công ty vì có thể có SDK cùng tên.
4. **Chọn frame liên quan:** trong stack của cause thích hợp, tìm frame ứng dụng gần điểm lỗi nhất; rồi xem các frame ứng dụng phía dưới để hiểu đầu vào và luồng gọi.
5. **Xác thực phiên bản code:** xác định jar/image/build/commit chính xác đã chạy. Mở file nguồn tương ứng, không tự động dùng bản mới nhất trên nhánh phát triển.
6. **Đọc ngữ cảnh quanh dòng:** xem câu lệnh, tham số, trạng thái trước đó, catch/rethrow, side effect, đường dữ liệu từ caller; có thể cần đọc thêm các frame trên/dưới.
7. **Tái hiện và sửa tại mức invariant:** thêm test chứng minh nguyên nhân, ghi nhận lỗi hợp lý và bảo đảm không chỉ thay đổi dòng in log; với lỗi race/async, cần kiểm tra thread và thời điểm completion.

Quy trình có tính lặp: sau khi đọc source, có thể thấy frame đang xét là một wrapper, từ đó quay lại cause sâu hơn hoặc một frame gọi phía dưới.

### 4.1. Chọn frame không phải là lọc bỏ thư viện

Nếu trace là:

~~~text
java.lang.IllegalArgumentException: negative length
    at java.base/java.util.Arrays.copyOf(Arrays.java:...)
    at com.example.app.DocumentService.copy(DocumentService.java:64)
    at com.example.app.RequestHandler.handle(RequestHandler.java:31)
~~~

Các dấu `...` là **chỗ minh họa không chứa số dòng thật**. Frame thư viện ở trên cho biết lỗi được phát hiện tại `Arrays.copyOf`; frame ứng dụng `DocumentService.java:64` có thể là nơi **truyền độ dài âm** vào thư viện. Cần kiểm tra chính logic tính toán kích thước/giá trị đầu vào tại đây, chứ không “sửa JDK” chỉ vì frame trên cùng thuộc `java.base`.

Ngược lại, nếu package đứng đầu là một thư viện bên thứ ba và lỗi nằm sâu trong nội bộ thư viện, có thể cần kiểm tra input/phiên bản dependency, mở source dependency đúng release, xem release notes hoặc tối giản case để báo lỗi thư viện. Đừng tự quy hết cho mã ứng dụng.

## 5. Ví dụ Java 17: trích frame ứng dụng và đối chiếu chính xác dòng

Ví dụ đầy đủ dưới đây ném `IllegalArgumentException` trong phương thức `parse`, qua các caller `load` và `endpoint`. `main` bắt exception, gọi `getStackTrace()` và chỉ in các frame của class ứng dụng.

Lưu chính xác thành file **`ApplicationFrameTraceDemo.java`**, bắt đầu từ dòng 1 của code block; không thêm dòng trống trước khai báo class nếu muốn số dòng trong output khớp:

~~~java
public class ApplicationFrameTraceDemo {
    static void parse(String value) {
        if (value.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
    }

    static void load() {
        parse(" ");
    }

    static void endpoint() {
        load();
    }

    public static void main(String[] args) {
        try {
            endpoint();
        } catch (IllegalArgumentException error) {
            System.out.println(error);
            for (StackTraceElement frame : error.getStackTrace()) {
                if (frame.getClassName().equals(ApplicationFrameTraceDemo.class.getName())) {
                    System.out.printf("%s(%s:%d)%n",
                            frame.getMethodName(), frame.getFileName(), frame.getLineNumber());
                }
            }
        }
    }
}
~~~

Từ thư mục chứa file, dùng JDK 17 trở lên:

~~~bash
javac --release 17 ApplicationFrameTraceDemo.java
java ApplicationFrameTraceDemo
~~~

Stdout chính xác của phiên bản source ở trên khi biên dịch với metadata dòng mặc định của `javac`:

~~~text
java.lang.IllegalArgumentException: name must not be blank
parse(ApplicationFrameTraceDemo.java:4)
load(ApplicationFrameTraceDemo.java:9)
endpoint(ApplicationFrameTraceDemo.java:13)
main(ApplicationFrameTraceDemo.java:18)
~~~

**Đối chiếu mã nguồn:**
- Dòng **4** là `throw new IllegalArgumentException(...)` trong `parse`. Đây là vị trí gây ra failure trong ví dụ.
- Dòng **9** là `parse(" ")` ở `load`, nơi đưa một chuỗi chỉ có khoảng trắng vào validation.
- Dòng **13** là `load()` trong `endpoint`.
- Dòng **18** là `endpoint()` bên trong `try` của `main`.

Số dòng phản ánh file được biên dịch, không phải số dòng của trang tài liệu hay cách trình bày được bọc thêm trong IDE. Nếu copy chương trình mà thêm import/comment/dòng trống ở phía trên, số dòng sẽ thay đổi tương ứng. Điều đó là chính xác; hãy mở nguồn **đúng trạng thái đã biên dịch**, không cố giữ số dòng của ví dụ bằng mọi giá.

Trong source này, mọi frame do ta in đều thuộc class `ApplicationFrameTraceDemo`. Trong ứng dụng thật có nhiều class trong cùng namespace, có thể lọc theo một hoặc nhiều prefix package, nhưng nên tránh chỉ lọc mỗi một class để không bỏ mất frame liên quan.

### 5.1. Từ trace sang hành động sửa

Chỉ nhìn vào dòng 4 thấy validation ném exception; đó là **hành vi đúng** nếu hàm yêu cầu tên không được rỗng. Nơi sửa có thể là:
- `load` truyền chuỗi `" "` không hợp lệ;
- một controller không kiểm tra/chuẩn hóa đầu vào;
- hoặc tài liệu API chưa nói rõ quy tắc giá trị hợp lệ.

Không nên xóa validation chỉ để hết stack trace. Cần hiểu invariant và đường dữ liệu qua các frame `load`, `endpoint`. Đây là điểm phân biệt **xác định chỗ exception xuất hiện** với **xác định nguyên nhân và sửa đúng lỗi**.

## 6. `-g:none`: class chạy được nhưng không còn thông tin dòng nguồn

Dùng chính file `ApplicationFrameTraceDemo.java` ở trên, biên dịch lại với:

~~~bash
javac --release 17 -g:none ApplicationFrameTraceDemo.java
java ApplicationFrameTraceDemo
~~~

Stdout từ môi trường Java 17 với chương trình này:

~~~text
java.lang.IllegalArgumentException: name must not be blank
parse(null:-1)
load(null:-1)
endpoint(null:-1)
main(null:-1)
~~~

Khi tắt thông tin debug bằng `-g:none`, phương thức `getFileName()` có thể trả `null` và `getLineNumber()` trả một giá trị âm (trong thí nghiệm này là `-1`). JVM vẫn biết tên class và method, nhưng **không thể đối chiếu trực tiếp số dòng** từ những frame đó.

Các tùy chọn cần biết:

| Tùy chọn biên dịch | Ý nghĩa chính |
| --- | --- |
| `javac Foo.java` | Mặc định thường có thông tin source và line cho stack trace |
| `javac -g Foo.java` | Sinh tất cả loại debug information được hỗ trợ, gồm line/source/local variables |
| `javac -g:lines,source Foo.java` | Yêu cầu metadata số dòng và file nguồn |
| `javac -g:none Foo.java` | Không sinh debug information |
| `javac --release 17 Foo.java` | Biên dịch theo API/target tương thích Java 17; không tự đảm bảo source hiện tại đúng với bản deploy |

Chỉ chứa tên class/method vẫn có thể hữu ích. Bạn có thể dùng `javap` để xem bytecode/line table nếu class có metadata; nếu artifact đã bị strip thông tin dòng thì không có lệnh thần kỳ nào khôi phục đúng line table từ một class chỉ còn tên method. Phải xác định artifact source/build hoặc tái hiện ở bản có debug info.

### 6.1. `javap -l` và `javap -c -l`

Với class được biên dịch trong thư mục hiện tại:

~~~bash
javap -l ApplicationFrameTraceDemo
javap -c -l ApplicationFrameTraceDemo
~~~

`javap -l` liệt kê line number table/local variable table khi có; `-c` giúp đối chiếu bytecode với code location. Output phụ thuộc phiên bản biên dịch và bytecode cụ thể, nên không có một stdout cố định cho mọi class ở đây.

Với jar, chỉ định đúng classpath và tên class fully-qualified:

~~~bash
javap -classpath path/to/app.jar -c -l com.example.app.Service
~~~

Lệnh này chỉ là ví dụ cấu trúc đường dẫn; đổi `path/to/app.jar` và tên class theo artifact thật. Nếu class do build/repackaging khác cung cấp, dùng đúng jar/image được runtime nạp chứ không dùng một thư viện khác có cùng FQCN.

Thông tin line table cho biết ánh xạ **bytecode offset → source line**; nó không lưu toàn bộ mã nguồn để bạn xem nội dung câu lệnh. Muốn biết code ở dòng 123, vẫn cần file source đúng phiên bản.

## 7. `StackTraceElement`: đọc frame bằng API thay vì phân tích chuỗi

Trong Java, `Throwable.getStackTrace()` trả mảng `StackTraceElement[]`. Mỗi phần tử cung cấp các trường đáng chú ý:

| Phương thức | Giá trị | Lưu ý |
| --- | --- | --- |
| `getClassName()` | Tên class khai báo frame | Có thể chứa `$` với nested/anonymous/generated class |
| `getMethodName()` | Tên phương thức | Có thể là `<init>`, `<clinit>`, `lambda$...` |
| `getFileName()` | Tên file nguồn hoặc `null` | Không phải đường dẫn tuyệt đối |
| `getLineNumber()` | Số dòng hoặc giá trị đặc biệt | Số âm không đại diện cho một dòng Java hợp lệ |
| `isNativeMethod()` | Frame có đại diện cho native method không | Không có một dòng Java tương ứng đơn giản |
| `getModuleName()` | Tên module nếu có | Có thể `null` |
| `getModuleVersion()` | Version module nếu có | Có thể `null` |
| `getClassLoaderName()` | Tên class loader nếu có | Có thể `null` |

Không nên parse chuỗi `"at "...` để tách file/dòng khi bạn **đang có `Throwable`**: dùng trực tiếp `StackTraceElement` chính xác hơn và không phụ thuộc khoảng trắng/prefix module. Khi chỉ có một file log text, bạn có thể dùng parser stacktrace phù hợp định dạng JVM, nhưng cần giữ nguyên cause/suppressed và các dòng `... N more`.

### 7.1. Chọn frame ứng dụng bằng predicate, không bằng vị trí cố định

Đây là **fragment minh họa**, có thể dùng bên trong một class đã import `java.util.Arrays`, `java.util.Optional` và có một `Throwable failure`:

~~~java
Optional<StackTraceElement> firstAppFrame =
        Arrays.stream(failure.getStackTrace())
                .filter(frame ->
                        frame.getClassName().startsWith("com.example.app."))
                .findFirst();
~~~

`firstAppFrame` chứa frame gần điểm exception nhất trong namespace đó, nếu có. Nhưng predicate này chỉ là **gợi ý lọc**:
- Ứng dụng có thể có nhiều package root.
- Một thư viện nội bộ dùng cùng prefix có thể không thuộc module chịu trách nhiệm.
- Framework/generator có thể tạo class đặt trong package ứng dụng.
- Exception có thể bắt nguồn ở `cause` khác, không phải `failure` ngoài cùng.

Cần xem đầy đủ trace, chọn đúng cause và module theo thông tin triển khai. Đừng xem `findFirst()` là thuật toán tự động xác định bug.

### 7.2. Lặp qua nguyên nhân, nhưng đừng viết vòng lặp không phòng vệ

Một exception có thể có nhiều lớp bao:

~~~text
CompletionException
    -> IllegalStateException
        -> IOException
~~~

Muốn xác định nguyên nhân cuối có thể đi theo `getCause()`, nhưng đừng quên:
- Một wrapper có thể mang ngữ cảnh nghiệp vụ quan trọng dù cause sâu là lỗi I/O.
- Không phải mọi `Throwable` bắt buộc có cause.
- Có thể có exception cố ý không lưu writable stack trace.
- Nếu code bên ngoài tạo chain bất thường, thuật toán tự động nên giới hạn sâu/chống lặp theo identity.

Fragment đơn giản:

~~~java
Throwable cursor = failure;
while (cursor.getCause() != null) {
    cursor = cursor.getCause();
}
System.out.println(cursor.getClass().getName());
~~~

Đây là fragment giả định `failure` đã tồn tại; nó mô tả trường hợp cause chain thông thường không có vòng. Khi làm công cụ phân tích log tổng quát, dùng một tập đối tượng đã duyệt theo **identity** hoặc giới hạn độ sâu để chống chain bất thường, thay vì giả định mọi đối tượng Throwable đều đến từ code chuẩn.

## 8. `Caused by`: frame nào là vị trí bọc, frame nào là lỗi gốc?

Ví dụ:

~~~text
java.lang.IllegalStateException: cannot start service
    at com.example.app.Bootstrap.start(Bootstrap.java:68)
    at com.example.app.Main.main(Main.java:21)
Caused by: java.io.IOException: config unreadable
    at com.example.app.ConfigReader.load(ConfigReader.java:43)
    at com.example.app.Bootstrap.start(Bootstrap.java:64)
    ... 1 more
~~~

Đây là trace minh họa. Phần **ngoài cùng** cho thấy `Bootstrap.start:68` bọc lỗi. `Caused by` cho thấy `ConfigReader.load:43` là nơi exception gốc được ghi nhận. Nếu chỉ đọc `Bootstrap.start:68` rồi bỏ qua cause, bạn dễ sửa nhầm tầng.

Cách đọc đúng:
1. Xác định exception ngoài cùng và tại sao nó được tạo: ví dụ `IllegalStateException("cannot start service")`.
2. Đi vào `Caused by` và xét loại lỗi gốc: `IOException`.
3. Tìm frame ứng dụng trong **trace của cause**.
4. Quay lại frame của wrapper để hiểu exception được chuyển đổi ở ranh giới nào và thông tin ngữ cảnh được thêm vào.
5. Dựa trên cả hai khối để ra quyết định: sửa đường dẫn/configuration, cải thiện message, xử lý retry hay báo lỗi.

### 8.1. `... N more` không phải N frame bị mất ngẫu nhiên

Khi `Throwable.printStackTrace()` in nhiều exception có chung phần cuối của stack, Java có thể rút gọn phần frame chung thành `... N more`. Đây là **ký pháp nén các frame trùng với stack của exception bao quanh**, không phải số dòng source bị ẩn, cũng không phải N exception chưa đọc.

Nếu cần xem đầy đủ object stack của từng cause trong code, `cause.getStackTrace()` vẫn cho mảng của cause đó (trừ khi stack trace được tùy biến/không ghi). Khi chỉ có log text rút gọn, hãy ghép các frame chung theo vị trí thích hợp hoặc dùng IDE/parser hỗ trợ. Không kết luận đường đi giữa hai lớp bị đứt chỉ vì xuất hiện `... 1 more`.

### 8.2. `throw e` và `throw new ...(..., e)` khác nhau

~~~java
try {
    callRepository();
} catch (IOException e) {
    throw e;
}
~~~

Đây là fragment giả định phương thức bao quanh cho phép `throws IOException`. Nó **ném lại cùng object exception** `e`; thông tin stack trace thường vẫn phản ánh vị trí nguồn đã thu thập, không được thay bằng một stack hoàn toàn mới chỉ vì rethrow.

Ngược lại:

~~~java
try {
    callRepository();
} catch (IOException e) {
    throw new IllegalStateException("loading report failed", e);
}
~~~

Đây là fragment; exception **mới** có stack riêng tại nơi bọc, và `e` trở thành cause với trace riêng. Cách bọc phù hợp khi muốn chuyển exception qua một ranh giới API, nhưng cần giữ `cause`. Nếu chỉ viết `throw new IllegalStateException(e.getMessage())`, bạn đã làm mất đường cause tự nhiên và khiến việc tìm frame gốc khó hơn.

## 9. `Suppressed`: lỗi khi cleanup cũng có stack riêng

Với `try-with-resources`, nếu body ném exception A và `close()` cũng ném exception B, B thường được đính kèm vào A dưới dạng **suppressed exception**, thay vì thay thế A làm exception chính.

Log có thể có:

~~~text
java.io.IOException: read failed
    at com.example.app.ConfigReader.read(ConfigReader.java:...)
    Suppressed: java.io.IOException: close failed
        at com.example.app.Resource.close(Resource.java:...)
    ...
~~~

Dấu `...` trong ví dụ là ký hiệu minh họa; khi chạy thật sẽ có file/line hoặc thông tin stack cụ thể.

Không coi `Suppressed` là vô nghĩa. Lỗi cleanup có thể báo mất khả năng flush dữ liệu, connection hỏng, khóa chưa được giải phóng hoặc một vấn đề hạ tầng quan trọng. Nhưng thường cần điều tra **lỗi chính A trước**, sau đó đánh giá B là hậu quả hay vấn đề độc lập.

### 9.1. Ví dụ Java 17 hoàn chỉnh cho cause và suppressed

Lưu file **`CauseAndSuppressedDemo.java`** đúng nội dung sau, bắt đầu tại dòng 1:

~~~java
import java.io.IOException;

public class CauseAndSuppressedDemo {
    static final class FailingResource implements AutoCloseable {
        @Override public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static void readConfig() throws IOException {
        try (FailingResource ignored = new FailingResource()) {
            throw new IOException("read failed");
        }
    }

    static void start() {
        try {
            readConfig();
        } catch (IOException cause) {
            throw new IllegalStateException("startup failed", cause);
        }
    }

    public static void main(String[] args) {
        try {
            start();
        } catch (IllegalStateException outer) {
            Throwable cause = outer.getCause();
            System.out.println("outer: " + outer.getMessage());
            System.out.println("cause: " + cause.getMessage());
            System.out.println("suppressed: "
                    + cause.getSuppressed()[0].getMessage());
            StackTraceElement first = cause.getStackTrace()[0];
            System.out.println("origin: " + first.getMethodName()
                    + "(" + first.getFileName() + ":" + first.getLineNumber() + ")");
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 CauseAndSuppressedDemo.java
java CauseAndSuppressedDemo
~~~

Stdout chính xác:

~~~text
outer: startup failed
cause: read failed
suppressed: close failed
origin: readConfig(CauseAndSuppressedDemo.java:12)
~~~

**Diễn giải:**

- Exception ngoài cùng là `IllegalStateException("startup failed")`, được tạo ở dòng **20**, trong `start()`.
- `getCause()` trả `IOException("read failed")`, được tạo/ném ở dòng **12**, trong `readConfig()`.
- Khi rời try-with-resources, `FailingResource.close()` lại ném `IOException("close failed")` ở dòng **6**. Vì body đã ném lỗi, lỗi đóng này được gắn vào `cause.getSuppressed()`.
- Vì code lấy frame đầu từ **cause**, giá trị `origin` phản ánh đúng `readConfig(...:12)` thay vì dòng bọc lỗi ở `start`.

Chương trình giả định có ít nhất một suppressed exception để tập trung vào cơ chế đã chủ động tạo. Trong thư viện tổng quát, phải kiểm tra độ dài mảng `getSuppressed()` trước khi truy cập chỉ số 0; nhiều exception bình thường không có lỗi suppressed nào.

### 9.2. Không áp quy tắc suppressed tùy tiện sang mọi callback

`try-with-resources` có ngữ nghĩa suppressed được Java quy định. Nhưng việc hai callback bất đồng bộ cùng ném exception, hoặc `whenComplete` action ném khi source đã thất bại, **không tự bảo đảm** callback exception xuất hiện trong `getSuppressed()` của lỗi gốc. Chỉ suy luận suppressed khi API/logic thực tế cam kết như vậy. Muốn ghi nhận hai lỗi độc lập, cần kênh quan sát hoặc kết quả tổng hợp được thiết kế trước.

## 10. Đối chiếu đúng dòng nguồn cần đúng phiên bản artifact

Giả sử log production nói:

~~~text
at com.example.billing.InvoiceService.issue(InvoiceService.java:142)
~~~

Nếu bạn mở source hiện tại và dòng 142 chỉ còn là một comment, không nên kết luận log sai. Có thể:
- Production chạy jar/image từ commit cũ.
- Nhánh đang mở đã thêm/xóa các dòng trước đó.
- Build đang dùng generated source hoặc annotation processing.
- Dependency có hai phiên bản hoặc nhiều copy trên classpath.
- Shadow/shading/obfuscation đã đổi tên class hoặc bố trí bytecode.
- Mã source được compile với tùy chọn strip debug thông tin.
- Một số class được biến đổi/instrument khi load.

**Số dòng trong stack trace tương ứng với class file đang chạy**, không tự động trỏ tới nhánh Git mới nhất. Quy trình đối chiếu:

1. Xác định phiên bản ứng dụng thực tế qua build ID, git commit, container image digest hoặc release artifact.
2. Kiểm tra tên class, module, jar chứa class mà runtime nạp.
3. Mở source tương ứng **đúng bản build đó**; trong monorepo, xác định đúng module.
4. Tới file/dòng được ghi trong trace; đọc khoảng 10–20 dòng xung quanh, không chỉ một dòng rời.
5. Đối chiếu thông tin line table từ class file nếu source và trace không khớp.
6. Nếu lỗi phụ thuộc concurrency/data, tái hiện cùng input/cấu hình/phiên bản dependency, không chỉ thay đổi code cho khớp vị trí dòng.

### 10.1. Tên file không đủ để xác định duy nhất source

Một repo có thể có nhiều file tên `Service.java` ở các module khác nhau. `StackTraceElement.getFileName()` thường chỉ trả tên file, không trả đường dẫn tuyệt đối. Cần ghép **tên class đầy đủ và package** để xác định file phù hợp.

Ví dụ tên `com.example.billing.internal.InvoiceService` thường tương ứng với một source path giống `com/example/billing/internal/InvoiceService.java` trong module sở hữu class. Nhưng class có thể được sinh hoặc biến đổi; đó là quy tắc tổ chức thông thường, không phải một ánh xạ tuyệt đối với mọi compiler.

Với nested class:
- `Outer$Inner` có thể nằm trong cùng `Outer.java`.
- `Outer$1` có thể là anonymous class hoặc class được compiler tạo.
- `Outer$$Lambda$...`/`lambda$method$0` có thể liên quan lambda, không có một file tên đúng bằng synthetic class.

Do đó không cố tìm một file tên `Outer$Inner.java` chỉ vì frame in ra tên binary class như vậy.

### 10.2. Trùng class trên classpath

Hai jar có cùng tên class có thể khiến chương trình nạp phiên bản khác bản bạn đang mở. Để điều tra code runtime, có thể truy vấn `ProtectionDomain`/`CodeSource` của class đang chạy trong môi trường phù hợp. Ví dụ fragment:

~~~java
var source = InvoiceService.class.getProtectionDomain().getCodeSource();
System.out.println(source == null ? "unknown" : source.getLocation());
~~~

Fragment giả định `InvoiceService` có sẵn; `CodeSource` có thể `null` đối với một số loại class loader/module, và vị trí trả về không phải bằng chứng đầy đủ của container/deployment provenance. Tuy nhiên nó có thể giúp tìm jar class được nạp. Không in đường dẫn máy chủ/URL nhạy cảm vào log công khai; dùng kênh chẩn đoán nội bộ.

### 10.3. Jar và class file có thể kiểm tra bằng công cụ JDK

Tìm tên class trong một jar bằng:

~~~bash
jar tf path/to/application.jar
~~~

Mở line number table của class:

~~~bash
javap -classpath path/to/application.jar -l com.example.billing.InvoiceService
~~~

Các dòng trên là **lệnh tham khảo**, không phải lệnh chạy được nguyên trạng vì tên file và class chỉ minh họa. `jar tf` liệt kê entries; `javap -l` đọc thông tin line/local variables từ class nếu có. Với executable fat jar hoặc custom class loader, classpath và layout có thể khác jar thông thường; cần xác minh class file thực thay vì áp câu lệnh một cách máy móc.

Để truy đến bytecode cụ thể, dùng `javap -c -l`. Vẫn cần hiểu lời gọi/invariant ở source; bytecode và line table không nói trực tiếp liệu dữ liệu đầu vào có đúng hay không.

## 11. Không nhầm stack trace của logger với trace của exception

Trong logging, ba trường hợp cần tách:

1. **Log exception object:** `logger.error("failed", e)` với logging framework hỗ trợ tham số Throwable thường in stack của `e`.
2. **Log chỉ message:** `logger.error("failed: {}", e.getMessage())` có thể chỉ in chuỗi, không có frames.
3. **Gọi `Thread.currentThread().getStackTrace()` hoặc `StackWalker` tại nơi log:** tạo ảnh chụp call stack của **thread hiện tại ở thời điểm log**, không nhất thiết là trace nơi exception ban đầu được tạo.

Ví dụ `e.printStackTrace()` in exception theo handler đang có; với chương trình thực tế, thường nên truyền `e` vào hệ thống logging có cấu trúc để giữ context/request ID thay vì in tự do vào stderr từ nhiều thread. Nhưng ngay cả logger tốt cũng không sửa được một exception đã mất cause do rethrow sai.

### 11.1. `Throwable.getStackTrace()` khác `StackWalker`

`Throwable.getStackTrace()` trả những frame gắn với một đối tượng Throwable. `StackWalker`, giới thiệu trong Java 9, có thể quan sát call stack của **thread hiện tại** theo API `walk`/`forEach`. Nó không cho bạn đọc ngược call stack đã biến mất của worker khác lúc trước chỉ vì bạn có một object Future.

Trong code async, khi `Future.get()` ném `ExecutionException` trên thread nhận kết quả, frame của `ExecutionException` và frame của cause có thể thuộc **hai giai đoạn/lớp thực thi khác nhau**. Muốn tìm worker làm gì, hãy xem `getCause().getStackTrace()`; không xem stack hiện tại của thread đang catch rồi kết luận worker ném lỗi ở dòng `get()`.

## 12. Lambda, reflection, proxy và framework làm frame khó đọc hơn

Không phải mọi frame ứng dụng đều in ra một tên method “đẹp”. Trong Java 17 có thể gặp:

~~~text
at com.example.app.TaskService.lambda$execute$0(TaskService.java:74)
at java.base/java.lang.reflect.Method.invoke(Method.java:...)
at jdk.proxy1/jdk.proxy1.$Proxy0.fetch(Unknown Source)
at com.example.app.TaskService.execute(TaskService.java:61)
~~~

Đây là **trace minh họa**, vị trí/dòng và tên proxy phụ thuộc runtime/compiler. Các kiểu frame thường gặp:

| Dấu hiệu | Cách đọc |
| --- | --- |
| `lambda$someMethod$0` | Method tổng hợp cho phần thân lambda; mở method nguồn tương ứng và tới dòng liên quan |
| `<init>` | Constructor |
| `<clinit>` | Static initializer |
| `$Proxy...`, `$$Enhancer...`, Byte Buddy/CGLIB | Class được sinh/ủy quyền; tìm callback/target class ứng dụng |
| `Method.invoke` hoặc `Constructor.newInstance` | Reflection; xem cause/target method hoặc exception bọc |
| `CompletableFuture$...` / `ForkJoinPool...` | Hạ tầng async; tìm lambda/callable ứng dụng và cause |
| `Thread.run` / executor worker | Điểm vào thread; thường không phải nơi cần sửa nghiệp vụ |

Một frame `lambda$run$0(MyService.java:74)` vẫn có thể trỏ chính xác đến dòng bên trong lambda của `MyService.java`. Không cần tìm class `lambda$run$0.java`.

### 12.1. Async không có một “stack xuyên luồng” thông thường

Khi công việc chuyển từ thread A sang executor B rồi callback C, call stack ở A không còn là phần “phía dưới” trong stack ở B. Vì thế trace của worker không nhất thiết chứa controller đã gửi task. Nếu thiếu mã tác vụ, request ID, trace ID hoặc context truyền xuyên async, bạn có thể không biết worker gắn với request nào.

Cách chẩn đoán:
- Gắn `operationId`/`correlationId` ngay khi gửi task.
- Ghi nhận điểm submit và mốc task bắt đầu/kết thúc khi cần.
- Thu lỗi qua `Future.get()`, `CompletableFuture.join()` và phân tích `getCause()`.
- Dùng tracing/instrumentation có hỗ trợ async context nếu hệ thống cần quan hệ xuyên nhiều thread/service.
- Đọc frame ứng dụng trong **trace thực sự của exception**, không suy ra caller không xuất hiện là không có liên quan.

Đừng gắn stack trace từ hai thread khác nhau vào nhau rồi coi là một call stack liên tục. Có thể kết hợp hai sự kiện bằng correlation ID, nhưng đó là **một quan hệ nghiệp vụ/điều phối**, không phải quan hệ call stack Java tự nhiên.

### 12.2. `CompletionException` và `ExecutionException`

Ví dụ một task do `CompletableFuture.supplyAsync` tạo ra ném `IllegalStateException`. Caller gọi `join()` có thể nhận `CompletionException`. Caller gọi `Future.get()` có thể nhận `ExecutionException`. Ở đây nên:
1. Ghi nhận wrapper để hiểu tầng nào quan sát lỗi.
2. Đọc `getCause()` để tìm lỗi worker.
3. Tìm frame ứng dụng ở stack của cause.
4. Không chỉ sửa dòng `future.join()` hoặc `future.get()` vì nó xuất hiện trong stack ngoài cùng.

Lưu ý timeout hoặc cancellation cũng có các kiểu exception riêng và không tự chứng minh công việc bên dưới đã dừng; việc thu được stack trace không thay thế quản lý trạng thái và side effect.

## 13. Dòng nguồn chỉ là điểm bắt đầu: phân tích ngữ cảnh

Sau khi tìm frame `OrderService.java:47`, vẫn phải đọc đủ ngữ cảnh:

- Đó là một lời gọi nào? Tham số được tính ở đâu? Giá trị null/rỗng/âm có thể lọt qua tầng trước không?
- Có branch riêng cho dữ liệu lỗi mà test chưa bao phủ?
- Dòng đó nằm trong vòng lặp hay stream? Phần tử gây lỗi nào?
- Lỗi đến từ một constructor/static initializer dùng lúc class load lần đầu?
- Có transaction đang mở? Side effect đã commit chưa?
- Có worker khác đang thay đổi cùng state không?
- Có lớp wrapper chỉ thêm message hoặc đổi exception type mà không giữ cause?
- Dòng đó tồn tại ở **release nào**, môi trường nào và build flags nào?

Một ví dụ thường gặp:

~~~java
return orders.get(index).customer().name().trim();
~~~

Đây là fragment minh họa. Một `NullPointerException` cùng chỉ về một dòng có nhiều thao tác dereference. Số dòng riêng không nói chính xác `orders`, `orders.get(index)`, `customer()` hay `name()` là null. Java hiện đại có thể phát sinh **helpful NullPointerException message** khi điều kiện phù hợp, nhưng không nên chỉ dựa vào nó. Đọc biểu thức, đưa dữ liệu vào các biến có tên nếu cần và thêm test với trạng thái cụ thể.

Một dòng gọi:

~~~java
repository.save(order);
~~~

có thể gây lỗi trong JDBC/transaction/framework. Dòng được chỉ trong service cho biết **đường gọi đến storage**, không nhất thiết code service là nơi nguyên nhân bắt đầu. Xem cause SQL exception, constraint violation, connection state và dữ liệu đầu vào để quyết định sửa.

## 14. Lỗi thường gặp khi đối chiếu file và số dòng

### 14.1. Mở nhánh mới nhất thay vì bản đang chạy

Nếu log thuộc image build cũ, line 87 của nhánh hiện tại có thể không liên quan. **Xác minh commit/tag/build ID trước khi sửa.** Đây là một trong những nguyên nhân phổ biến khiến kỹ sư “không tìm thấy dòng gây lỗi”.

### 14.2. Tìm file bằng tên mà không xét package/module

`Service.java` có thể tồn tại nhiều nơi. Dùng FQCN và module/jar của class, không chỉ tên `FileName.java`.

### 14.3. Lấy frame ứng dụng đầu tiên của exception ngoài cùng rồi bỏ cause

Exception ngoài cùng có thể là wrapper. Đọc `Caused by`, nhất là với I/O, JDBC, reflection và CompletableFuture.

### 14.4. Xem `... N more` là những dòng bị mất

Nó mô tả suffix frames trùng giữa các trace, không phải ngẫu nhiên stack bị cắt. Tuy nhiên logger/thư viện cũng có thể **truncate** stacktrace thật sự do cấu hình; cần phân biệt hai hiện tượng.

### 14.5. Cho rằng mỗi frame phải có tên file và số dòng

`Unknown Source`, `Native Method`, class sinh động, class biên dịch `-g:none` hoặc source map đặc biệt có thể thiếu số dòng. Không bịa line number; tìm bằng method, bytecode, source/build và reproduction.

### 14.6. “Sửa” frame thư viện đầu tiên

Có thể lỗi do ứng dụng truyền tham số sai; đọc frame ứng dụng gần nhất và invariant đầu vào. Nhưng cũng đừng loại trừ lỗi thư viện nếu bằng chứng chỉ vào internal bug.

### 14.7. Chỉ tìm đoạn `throw`, không tìm nơi tạo exception

Một Throwable có thể được tạo trước khi ném hoặc bị dùng lại; trace gắn với thông tin thu thập stack của object, không nhất thiết là dòng `throw e` gần nhất. Tìm cách exception được tạo và rethrow.

### 14.8. Log `e.getMessage()` thay vì cả throwable

Message không chứa stack trace, cause và suppressed. Khi chẩn đoán lỗi không rõ, log throwable trong kênh nội bộ đáng tin, đồng thời kiểm soát thông tin nhạy cảm và khối lượng log.

### 14.9. Bỏ exception trong `Suppressed`

Lỗi cleanup có thể cung cấp manh mối thứ hai rất quan trọng; kiểm tra `getSuppressed()` khi có try-with-resources.

### 14.10. Coi frame của thread đang catch là frame của worker

Exception qua Future/CompletableFuture có wrapper tại thread caller; lỗi gốc có trace của thread thực thi task. Giữ hai lớp chứng cứ tách biệt.

## 15. Kiểm thử và công cụ để chứng minh ánh xạ

Một chu trình QA nhỏ, lặp được:

1. Viết một đoạn tạo lỗi có kiểm soát trong một file Java nhỏ.
2. Biên dịch bằng đúng mức Java cần hỗ trợ, ví dụ `javac --release 17`.
3. Gọi `Throwable.getStackTrace()` và in `getClassName()`, `getMethodName()`, `getFileName()`, `getLineNumber()`.
4. Mở file source đã biên dịch, đếm dòng và xác nhận các call sites.
5. Biên dịch lại cùng file với `-g:none`; quan sát việc mất tên file/line nhưng vẫn có class/method.
6. Nếu cần, dùng `javap -c -l` để đọc line number table tương ứng.
7. Thêm wrapper `throw new ...(..., e)`, rồi xác nhận trace ngoài và trace cause trỏ tới hai vị trí khác nhau.
8. Thêm try-with-resources mà `close()` ném để xác nhận suppressed exception.
9. Khi làm trên hệ thống thật, lặp lại bằng **artifact production có thể kiểm chứng**, không dùng file Java test để suy ra mọi môi trường đều giống nhau.

### 15.1. Ví dụ với JUnit 5

Đây là **fragment test**, giả định JUnit 5 đã được cấu hình, class `ApplicationFrameTraceDemo` được đặt trong phạm vi test, và có static import `assertThrows`, `assertEquals`, `assertTrue`:

~~~java
IllegalArgumentException ex = assertThrows(
        IllegalArgumentException.class,
        () -> ApplicationFrameTraceDemo.parse(" "));

StackTraceElement top = ex.getStackTrace()[0];
assertEquals("parse", top.getMethodName());
assertEquals("ApplicationFrameTraceDemo.java", top.getFileName());
assertTrue(top.getLineNumber() > 0);
~~~

Thường không nên hardcode số dòng 4 trong test unit nghiệp vụ, vì một comment được thêm ở đầu file sẽ làm test vỡ dù chương trình vẫn đúng. Khi chủ đích là **bài tập kiểm chứng line table**, việc đối chiếu với số dòng thật là hợp lệ; nhưng với unit test sản phẩm, nên assert loại exception/message/invariant, chỉ kiểm tra line number dương nếu muốn đảm bảo debug metadata.

### 15.2. Khi log thiếu dòng source trong production

Bảng kiểm tra:

| Dấu hiệu | Bước kiểm tra hợp lý |
| --- | --- |
| Frame có `(Unknown Source)` | Kiểm tra class file debug metadata và compiler/proguard settings |
| Frame ghi file/dòng nhưng không khớp repo | Kiểm tra build ID, commit, generated source và jar đang chạy |
| Frame thuộc `lambda$...` | Mở method bao lambda và dòng source tương ứng |
| Frame thuộc `$Proxy...` | Xác định target method, interceptor và cause |
| Chỉ thấy `CompletionException`/`ExecutionException` | Mở `getCause()`, xem trace của task gốc |
| Trace bị cắt bởi cấu hình logger | Điều chỉnh policy log stack trace có giới hạn và bảo vệ dữ liệu |
| Nhiều exception trùng tên message | Dựa vào timestamp, correlation ID, class/method/cause, không chỉ text message |
| Lỗi chỉ xuất hiện dưới tải | Thu thread/trace context, input, trạng thái chia sẻ; tái hiện race có điều phối |
| Số dòng âm | Kiểm tra `-g` và line table; đừng đoán line từ tên method |

## 16. Logging an toàn và đủ ngữ cảnh

Trong ứng dụng production, nên ghi đủ dữ liệu chẩn đoán nhưng tránh lộ thông tin nhạy cảm:

- **Exception type + cause chain**: biết lỗi nào thật sự phát sinh và nơi bị bọc.
- **Stack frame ứng dụng đáng chú ý**: class, method, file, line; nhưng giữ trace đầy đủ trong kênh nội bộ khi cần.
- **Correlation ID hoặc operation ID**: nối log trên các thread/tác vụ.
- **Build/release ID**: xác định source chính xác.
- **Thread name và module/service**: biết môi trường chạy.
- **Các thuộc tính nghiệp vụ an toàn**: trạng thái, loại thao tác, mã lỗi ổn định; tránh raw token, mật khẩu, dữ liệu cá nhân, SQL chứa thông tin nhạy cảm.

Tránh hai cực đoan: chỉ log `e.toString()` khiến thiếu chứng cứ, hoặc log toàn bộ request payload/token khiến rò rỉ thông tin. Dùng công cụ logging có structured fields, cấu hình level và policy retention phù hợp; không tự tạo một log line cực dài chứa tất cả dữ liệu.

### 16.1. Log một lần tại ranh giới phù hợp

Một exception có thể bị log ở repository, service, controller rồi lại bị log ở job handler, tạo nhiều stacktrace giống nhau. Thông thường nên **giữ cause khi chuyển tầng** và chọn điểm logging sở hữu việc báo lỗi, thay vì log-error rồi rethrow cùng exception ở mọi nơi. Tuy nhiên vẫn có tình huống mỗi tầng có metric hoặc audit riêng; khi đó thông tin nên được phân biệt rõ để không nhân số lượng sự cố thực tế.

Nếu một phương thức catch để phục hồi thành công, có thể ghi metric recovery phù hợp thay vì phát log lỗi mức cao như thể request cuối đã thất bại. Một stack trace có ý nghĩa khi nó được liên hệ với **trạng thái xử lý cuối cùng**.

## 17. Cây quyết định từ một frame đến hướng điều tra

~~~text
Có stack trace từ Java
|
+-- Có Caused by / Suppressed?
|     +-- Có -> đọc các trace riêng và xác định lỗi chính
|     +-- Không -> bắt đầu từ throwable hiện có
|
+-- Frame trên cùng thuộc ứng dụng?
|     +-- Có -> đối chiếu file:line, rồi xem caller phía dưới
|     +-- Không -> tìm frame ứng dụng gần đó và kiểm tra input/cause
|
+-- Có số dòng hợp lệ?
|     +-- Có -> mở đúng phiên bản source, xem vùng xung quanh dòng
|     +-- Không -> kiểm tra debug info/class/jar/generated source
|
+-- Có chắc source đúng artifact deploy?
|     +-- Không -> xác minh release/build/commit/classloader
|     +-- Có -> đối chiếu biểu thức, invariant, trạng thái thực
|
+-- Có thể tái hiện?
      +-- Có -> viết test cụ thể và sửa nguyên nhân
      +-- Không -> bổ sung telemetry an toàn và chẩn đoán race/async
~~~

Cây quyết định là phương pháp định hướng, không phải một chương trình tự động suy ra bug. Mục tiêu là rút ngắn thời gian đi từ **triệu chứng trong log** đến **nguyên nhân có thể chứng minh bằng mã và dữ liệu**.

## 18. Checklist khi đọc stack trace Java

- [ ] Đã giữ stack trace đủ dòng, bao gồm `Caused by`, `Suppressed` và `... N more` nếu có.
- [ ] Đã phân biệt exception ngoài cùng, exception gốc và lỗi cleanup.
- [ ] Đã tìm frame ứng dụng **trong trace của cause phù hợp**, không chỉ ở trace ngoài.
- [ ] Đã đọc đúng `class.method(File.java:line)`, bao gồm module/class loader prefix khi có.
- [ ] Đã đối chiếu đúng package, module, jar/image và build/commit triển khai.
- [ ] Đã xem source quanh dòng và các caller, không chỉ chỉnh dòng đầu trace.
- [ ] Đã cân nhắc lambda, constructor, static initializer, generated proxy, reflection và async wrapper.
- [ ] Đã hiểu rằng `Unknown Source`/line âm thường là giới hạn thông tin, không phải số dòng để đoán.
- [ ] Đã xác minh debug metadata khi source line thiếu hoặc lệch; dùng `javap -l` nếu phù hợp.
- [ ] Đã giữ `cause` khi wrap exception và không làm mất chứng cứ bằng cách chỉ log message.
- [ ] Đã phân biệt trace của exception với stack snapshot tại nơi log.
- [ ] Đã kiểm tra trạng thái nghiệp vụ, dữ liệu đầu vào, side effect và concurrency trước khi kết luận nguyên nhân.
- [ ] Đã thêm test chứng minh nguyên nhân/sửa chữa, không viết test quá dễ vỡ vì hardcode line number của source đang phát triển.
- [ ] Đã bảo vệ dữ liệu nhạy cảm và kiểm soát log volume trong production.

### Bài tập thực hành

Giả sử một dịch vụ xuất hóa đơn ném `CompletionException` khi callback nhận dữ liệu bất đồng bộ thất bại. Trace có các frame từ `CompletableFuture`, một `InvoiceService.lambda$generate$0` và một cause `SQLException`.

1. Chỉ rõ vì sao không nên sửa dòng `future.join()` chỉ vì wrapper xuất hiện ở đó.
2. Tìm cause sâu nhất và frame ứng dụng gần điểm lỗi, sau đó truy ngược caller để xác định dữ liệu đầu vào.
3. Kiểm tra bản artifact đang deploy có đúng với source IDE không và dùng `javap -l` khi dòng lệch.
4. Nếu `SQLException` bị bọc trong `IllegalStateException` nhưng không giữ cause, giải thích phần chứng cứ nào mất đi.
5. Nếu task đã ghi file rồi mới thất bại, giải thích vì sao chẩn đoán được frame ném lỗi **không đồng nghĩa file đã rollback**.
6. Viết một test cố tình truyền dữ liệu sai đến `InvoiceService`, ghi nhận exception và xác minh loại lỗi, cause, mã nghiệp vụ; không dựa vào một số dòng cố định để test chức năng.

**Kết luận:** Frame ứng dụng giúp xác định **một vị trí trong đường thực thi**, nhưng chẩn đoán đúng cần đi cùng **cause/suppressed, ngữ cảnh caller và đúng bản nguồn đã biên dịch**. Đọc `File.java:line` là bước bắt đầu điều tra, không phải lời phán quyết rằng dòng đó luôn là bug cần sửa.