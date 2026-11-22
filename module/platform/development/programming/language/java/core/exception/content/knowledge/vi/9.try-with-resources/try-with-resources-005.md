# Thứ tự tạo tài nguyên từ trái sang phải trong try-with-resources

> Java Core – Exception · Nhóm: Try-with-resources · Java 17+.

## 1. Quy tắc và phạm vi bài học

Khi một câu lệnh `try-with-resources` khai báo nhiều tài nguyên, Java **đánh giá initializer từ trái sang phải**, rồi mới chạy thân `try`. Khi rời thân, Java **đóng những tài nguyên đã khởi tạo thành công theo thứ tự từ phải sang trái**. Quy tắc này vẫn áp dụng khi thân try ném ngoại lệ hoặc khi một initializer phía sau bị lỗi.

~~~java
try (Resource a = createA();
     Resource b = createB();
     Resource c = createC()) {
    useResources();
}
~~~

Đây là mã minh họa, cần định nghĩa kiểu `Resource` triển khai `AutoCloseable` và các hàm tương ứng. Nếu không có lỗi, trình tự là:

~~~text
createA() → createB() → createC() → useResources()
                                → c.close() → b.close() → a.close()
~~~

Nếu `createB()` ném lỗi: A được đóng, C **không được khởi tạo**, thân try **không chạy**, và catch bên ngoài nhận exception sau bước cleanup. Đừng nhầm “initializer B đã bắt đầu” với “B đã được khởi tạo thành công và được đăng ký để đóng”.

## 2. Cách đọc resource specification

~~~java
try (TypeA a = openA();
     TypeB b = openB()) {
    process(a, b);
} catch (IOException ex) {
    handle(ex);
}
~~~

Đoạn này chỉ biểu diễn cấu trúc, chưa độc lập. Các điều kiện chính:

- Biến tài nguyên phải có kiểu tương thích `AutoCloseable`. Ví dụ thư viện chuẩn: `InputStream`, `BufferedReader`, `java.sql.Connection`.
- Dấu `;` phân cách resource declarations. Dấu cuối trước ngoặc đóng là tùy chọn.
- Initializer A phải hoàn thành **bình thường** trước khi initializer B được đánh giá.
- Nếu initializer B thất bại, tài nguyên A đã khởi tạo thành công vẫn được đóng tự động; B không được đóng nếu chưa được tạo/nhận thành công.
- Resource declarations là các biến `final`, không được gán lại trong body.
- Resource khác null được đóng **ngược với thứ tự trong header**; resource null được bỏ qua ở bước đóng tự động.
- Khi một lần close ném lỗi, Java vẫn cố đóng những resource còn lại theo quy tắc ngôn ngữ.
- Cơ chế này có từ **Java 7**. Viết `try (existingVariable)` với biến final/effectively final đã khai báo trước được hỗ trợ từ **Java 9**.

Một initializer không nhất thiết chứa `new`; nó có thể là lời gọi factory, mở file hoặc kết hợp nhiều phép toán. Điều Java bảo đảm là **thứ tự đánh giá các biểu thức**. Các side effect đã xảy ra trong factory không tự rollback nếu factory cuối cùng ném ngoại lệ.

## 3. Ví dụ Java 17 hoàn chỉnh và có thể chạy

Tạo file **`ResourceOrderDemo.java`**. Lớp `TracedResource` thực thi `AutoCloseable`, ghi lại mỗi lần mở/đóng và tạo ngoại lệ giả lập theo cấu hình.

~~~java
import java.io.IOException;

public class ResourceOrderDemo {
    private static final class TracedResource implements AutoCloseable {
        private final String name;
        private final boolean failClose;

        TracedResource(String name, boolean failOpen, boolean failClose)
                throws IOException {
            System.out.println("open " + name);
            if (failOpen) {
                throw new IOException("open " + name + " failed");
            }
            this.name = name;
            this.failClose = failClose;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            if (failClose) {
                throw new IOException("close " + name + " failed");
            }
        }
    }

    private static TracedResource open(
            String name, boolean failOpen, boolean failClose)
            throws IOException {
        return new TracedResource(name, failOpen, failClose);
    }

    private static void report(IOException ex) {
        System.out.println("caught=" + ex.getMessage());
        for (Throwable suppressed : ex.getSuppressed()) {
            System.out.println("suppressed=" + suppressed.getMessage());
        }
    }

    private static void normal() {
        System.out.println("== normal ==");
        try (TracedResource a = open("A", false, false);
             TracedResource b = open("B", false, false);
             TracedResource c = open("C", false, false)) {
            System.out.println("body");
        } catch (IOException ex) {
            report(ex);
        }
    }

    private static void failedSecond() {
        System.out.println("== failed second ==");
        try (TracedResource a = open("A", false, false);
             TracedResource b = open("B", true, false);
             TracedResource c = open("C", false, false)) {
            System.out.println("body");
        } catch (IOException ex) {
            report(ex);
        }
    }

    private static void failedThirdAndClose() {
        System.out.println("== failed third + close ==");
        try (TracedResource a = open("A", false, true);
             TracedResource b = open("B", false, true);
             TracedResource c = open("C", true, false)) {
            System.out.println("body");
        } catch (IOException ex) {
            report(ex);
        }
    }

    private static void failedBodyAndClose() {
        System.out.println("== failed body + close ==");
        try (TracedResource a = open("A", false, true);
             TracedResource b = open("B", false, true)) {
            System.out.println("body");
            throw new IOException("body failed");
        } catch (IOException ex) {
            report(ex);
        }
    }

    private static void failedCloseOnly() {
        System.out.println("== failed close only ==");
        try (TracedResource a = open("A", false, true);
             TracedResource b = open("B", false, true)) {
            System.out.println("body");
        } catch (IOException ex) {
            report(ex);
        }
    }

    private static void nullResource() {
        System.out.println("== null resource ==");
        try (TracedResource a = null;
             TracedResource b = open("B", false, false)) {
            System.out.println("body");
        } catch (IOException ex) {
            report(ex);
        }
    }

    private static void referenceJava9() {
        System.out.println("== variable reference (Java 9+) ==");
        try {
            final TracedResource resource = open("X", false, false);
            try (resource) {
                System.out.println("body");
            }
        } catch (IOException ex) {
            report(ex);
        }
    }

    public static void main(String[] args) {
        normal();
        failedSecond();
        failedThirdAndClose();
        failedBodyAndClose();
        failedCloseOnly();
        nullResource();
        referenceJava9();
    }
}
~~~

Biên dịch/chạy từ thư mục chứa file:

~~~bash
javac --release 17 -encoding UTF-8 ResourceOrderDemo.java
java ResourceOrderDemo
~~~

**Stdout chính xác** đã được kiểm chứng bằng chương trình Java biên dịch thực tế:

~~~text
== normal ==
open A
open B
open C
body
close C
close B
close A
== failed second ==
open A
open B
close A
caught=open B failed
== failed third + close ==
open A
open B
open C
close B
close A
caught=open C failed
suppressed=close B failed
suppressed=close A failed
== failed body + close ==
open A
open B
body
close B
close A
caught=body failed
suppressed=close B failed
suppressed=close A failed
== failed close only ==
open A
open B
body
close B
close A
caught=close B failed
suppressed=close A failed
== null resource ==
open B
body
close B
== variable reference (Java 9+) ==
open X
body
close X
~~~

Các exception mẫu có message do chương trình tạo nên output không phụ thuộc ngôn ngữ hệ điều hành. Toàn bộ chương trình biên dịch được với `--release 17`, không cần thư viện ngoài.

## 4. Phân tích từng tình huống

### 4.1. Thành công với ba tài nguyên

Nhánh `normal()` in lần lượt `open A`, `open B`, `open C`; lúc ấy body mới in `body`. Sau body, Java gọi `c.close()`, `b.close()`, `a.close()`. Nếu ba tài nguyên có quan hệ phụ thuộc như A là nguồn, B bọc A và C bọc B, thứ tự đóng đảo ngược giúp phần phụ thuộc được giải phóng trước phần nền tảng.

### 4.2. B lỗi khi khởi tạo

Trong `failedSecond()`, A thành công; constructor B in `open B` rồi ném `IOException("open B failed")`. Do vậy:

1. C **chưa được khởi tạo**, vì initializer của B chưa hoàn tất bình thường.
2. Body **không được vào**, vì cả danh sách tài nguyên chưa thành công.
3. B chưa được nhận là resource đã khởi tạo thành công nên try-with-resources **không gọi B.close()**.
4. Java tự gọi `a.close()`, in `close A`.
5. Sau khi cleanup A, catch in `caught=open B failed`.

Đây là bằng chứng rằng try-with-resources quản lý các tài nguyên đã khởi tạo thành công **ngay cả khi thân try chưa bao giờ bắt đầu**.

### 4.3. C mở lỗi, B và A lỗi đóng

Trong `failedThirdAndClose()`, A/B mở thành công, C bắt đầu rồi thất bại. B.close() và A.close() cùng ném lỗi, nhưng Java vẫn cố đóng theo thứ tự **B rồi A**. Primary exception là lỗi mở C. Hai lỗi đóng được thêm vào `getSuppressed()` của primary:

~~~text
Primary:    open C failed
Suppressed: close B failed
Suppressed: close A failed
~~~

Không có `close C` vì C chưa khởi tạo thành công. Catch được thực thi **sau bước cleanup**.

### 4.4. Body ném lỗi

Trong `failedBodyAndClose()`, A và B đều mở thành công, body in `body` rồi ném `IOException("body failed")`. B/A được đóng theo thứ tự ngược; lỗi đóng trở thành suppressed của **lỗi body**. Khác trường hợp 4.3, body đã thực sự bắt đầu, nhưng quy tắc đóng giống nhau.

### 4.5. Chỉ có lỗi ở close

Trong `failedCloseOnly()`, body thành công. B.close() chạy trước và ném lỗi, A.close() tiếp tục chạy và cũng ném lỗi. **Lỗi B là primary** vì là lỗi đóng đầu tiên; lỗi A là suppressed. Thành công trong body không bảo đảm cả try-with-resources thành công, bởi close cũng có thể thất bại.

### 4.6. Resource nhận null

Trong `nullResource()`, A có giá trị null, B được mở bình thường. Java **không gọi close trên null**; B vẫn được đóng. Đây là quy tắc của cơ chế tự động, không có nghĩa việc dereference A trong body là an toàn: thao tác gọi method qua A có thể ném `NullPointerException`.

### 4.7. Resource reference từ Java 9

Trong `referenceJava9()`, biến `resource` được tạo trước header, sau đó mới dùng `try (resource)`. Java 9 cho phép biến final hoặc effectively final đã tồn tại làm tài nguyên trong header. Resource được đóng sau body, nhưng **bước tạo X ở trước try**; nếu việc mở X thất bại, header `try (resource)` chưa được bắt đầu.

## 5. Ranh giới cleanup khi initializer thất bại

Cần phân biệt **bắt đầu khởi tạo** và **được đăng ký thành công**. Một factory có thể mở socket hoặc tệp trung gian, sau đó ném exception trước khi trả về resource cuối cùng. Try-with-resources ở caller không tự biết các tài nguyên trung gian đó; **factory phải tự cleanup trước khi thoát vì lỗi**.

Ví dụ minh họa chưa độc lập:

~~~java
static Wrapper create() throws IOException {
    InputStream stream = Files.newInputStream(path);
    return buildWrapper(stream);
}
~~~

Nếu `buildWrapper(stream)` thất bại, stream đã được mở nhưng caller chưa nhận một Wrapper. Mã trên cần được sửa để bảo vệ stream trong trường hợp tạo wrapper lỗi; tên `Wrapper`, `path` và `buildWrapper` cũng chưa được định nghĩa ở ví dụ này.

Ngược lại, nếu A được khai báo như resource đầu tiên của try rồi B được tạo từ A và B thất bại, A đã được quản lý và sẽ được đóng. Thiết kế **ownership** và thứ tự khai báo làm khác biệt rất lớn.

## 6. Suppressed exception và ngoại lệ chính

Try-with-resources bảo toàn ngoại lệ quan trọng hơn bằng cơ chế suppressed:

| Trường hợp | Primary | Suppressed |
| --- | --- | --- |
| Initializer C lỗi; đóng A/B bình thường | Lỗi C | Không có |
| Initializer C lỗi; B/A đóng lỗi | Lỗi C | Lỗi B rồi A |
| Body lỗi; B/A đóng lỗi | Lỗi body | Lỗi B rồi A |
| Body bình thường; B/A đóng lỗi | Lỗi B.close() | Lỗi A.close() |
| Mọi thao tác bình thường | Không có | Không có |

Để chẩn đoán trong một catch thích hợp:

~~~java
catch (IOException ex) {
    System.out.println("primary=" + ex.getMessage());
    for (Throwable child : ex.getSuppressed()) {
        System.out.println("suppressed=" + child.getMessage());
    }
}
~~~

Đây là đoạn minh họa trong cấu trúc try/catch phù hợp. `getSuppressed()` không giống `getCause()`: cause mô tả chuỗi nguyên nhân của exception được bọc; suppressed lưu các ngoại lệ thứ cấp phát sinh trong cleanup.

Một chuỗi close thủ công như:

~~~java
b.close();
a.close();
~~~

có thể dừng ngay tại B nếu B.close() ném exception. Try-with-resources có ngữ nghĩa đặc biệt để **tiếp tục cố đóng tài nguyên còn lại** và bảo toàn thông tin lỗi.

## 7. Catch, finally và return

Với cấu trúc:

~~~java
try (Resource a = openA();
     Resource b = openB()) {
    process();
} catch (IOException ex) {
    handle(ex);
} finally {
    afterAll();
}
~~~

Đây là cú pháp minh họa, không độc lập. Những tài nguyên đã được mở sẽ được đóng trước khi catch tương ứng chạy; finally bên ngoài chạy theo quy tắc của nó sau đó.

Khi body chứa `return expression;`, biểu thức return được đánh giá trước khi rời try, nhưng tài nguyên vẫn được đóng trước khi caller nhận kết quả. Một lỗi đóng có thể khiến phương thức ném exception thay vì hoàn thành return. Ví dụ:

~~~java
static String firstLine(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
~~~

Đây là một phương thức minh họa cần được đặt trong class và import các API I/O liên quan.

## 8. Thực hành và lỗi phổ biến

- **Nhầm hai chiều:** initializer trái→phải, close phải→trái.
- **Tưởng body chạy sau A dù B lỗi:** body chỉ chạy khi tất cả initializer thành công.
- **Tưởng B được close khi constructor B bắt đầu rồi ném:** B chưa được bàn giao thành công cho header, nên caller chưa quản lý nó.
- **Quên tài nguyên bên trái khi initializer bên phải lỗi:** Java đóng chúng tự động.
- **Tưởng close của B ném thì A không được đóng:** Java vẫn cố đóng A.
- **Chỉ ghi log primary:** có thể bỏ sót lỗi đóng trong suppressed.
- **Nhầm suppressed với cause:** hai quan hệ exception khác nhau.
- **Đăng ký cả wrapper và resource nền mà không xem Javadoc:** wrapper có thể tự đóng resource bên dưới, gây đóng trùng.
- **Gán lại biến resource:** biến trong resource declaration là final.
- **Dùng cú pháp resource reference từ Java 9 trong dự án Java 8:** không tương thích nguồn.
- **Cho rằng null resource luôn ném NPE trong bước close:** null bị bỏ qua ở bước close tự động.
- **Tưởng try-with-resources rollback mọi side effect:** nó quản lý close, không thay thế transaction.
- **Không kiểm tra tình huống initializer thất bại một phần:** factory cần tự giải phóng tài nguyên nội bộ.

Cách suy luận nhanh: đánh số A, B, C từ trái sang phải; xác định initializer đầu tiên có thể ném; giữ danh sách resource đã hoàn thành trước đó; đảo danh sách này để xác định thứ tự đóng; cuối cùng xác định primary/suppressed và handler nhận lỗi.

## 9. Tự đánh giá

**Câu 1.** Với A, B, C, nếu B mở lỗi thì C có được mở không?

*Không.* Java dừng đánh giá những initializer bên phải. A đã mở được đóng và body không chạy.

**Câu 2.** Nếu A, B, C thành công, thứ tự đóng thế nào?

*C → B → A.*

**Câu 3.** Nếu C mở lỗi rồi B.close() và A.close() cùng lỗi?

*Lỗi khởi tạo C là primary; lỗi đóng B rồi A là suppressed.*

**Câu 4.** Nếu body bình thường nhưng B.close() và A.close() cùng lỗi?

*Lỗi B.close() là primary vì B đóng trước; lỗi A.close() là suppressed.*

**Câu 5.** Nếu A=null và B hợp lệ?

*Java bỏ qua A.close(); B vẫn được mở và đóng theo quy tắc.*

**Câu 6.** Vì sao constructor B có thể gây rò rỉ khi thất bại dù caller dùng try-with-resources?

*B có thể đã mở các đối tượng trung gian trước khi trả kết quả cho caller; constructor/factory phải tự cleanup những đối tượng ấy.*

**Câu 7.** §try (existingResource)§ cần Java phiên bản nào?

*Cú pháp resource reference trực tiếp có từ Java 9; biến phải final/effectively final.*

## 10. Tài liệu tham khảo

- [JLS Java SE 17, mục 14.20.3 – try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3) – resource specification và quản lý tài nguyên.
- [JLS Java SE 17, mục 14.20.3.1 – Basic try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3.1) – thứ tự đóng và cơ chế mở rộng tương đương.
- [JLS Java SE 17, mục 14.20.3.2 – Extended try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3.2) – catch/finally bên ngoài.
- [Java SE 17 API – AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html) – hợp đồng close.
- [Java SE 17 API – Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed()) – ngoại lệ bị suppressed.
- [Oracle Java Tutorials – try-with-resources](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html) – ví dụ cú pháp từ Java 7.

**Kết luận:** Java **đánh giá initializer từ trái sang phải**, chỉ chạy body khi mọi initializer thành công, rồi **đóng các resource khác null đã khởi tạo thành công từ phải sang trái**. Lỗi ở resource phía sau không ngăn đóng các resource phía trước; lỗi cleanup bổ sung được lưu trong §getSuppressed()§.