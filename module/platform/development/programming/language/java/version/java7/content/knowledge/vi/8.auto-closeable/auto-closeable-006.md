# Ủy quyền đóng các tài nguyên thành phần với `AutoCloseable`

## 1. Mục tiêu và bối cảnh

Một đối tượng có thể **sở hữu nhiều tài nguyên thành phần**: ví dụ một phiên xử lý dữ liệu sở hữu luồng đầu vào, bộ giải mã và bộ đệm; một client sở hữu kết nối và các đối tượng được mở từ kết nối ấy; hoặc một đối tượng quản lý phiên làm việc mở nhiều file, kênh và handle có vòng đời chung.

Nếu đối tượng tổng hợp (*composite*) triển khai `AutoCloseable`, người dùng có thể viết:

~~~java
try (CompositeSession session = openSession()) {
    session.process();
}
~~~

Đây là **đoạn minh họa**, giả định `CompositeSession` và `openSession()` do ứng dụng định nghĩa. Khi rời `try-with-resources`, Java gọi **`session.close()`**. Tuy nhiên, chỉ có việc composite implement `AutoCloseable` **không làm JVM tự duyệt các field để đóng các đối tượng con**. Chính implementation của `CompositeSession.close()` phải quyết định **thành phần nào thuộc quyền sở hữu**, **thứ tự đóng**, **cách thử đóng các thành phần còn lại khi một lần đóng lỗi**, và **cách báo lỗi**.

Bài này tập trung vào **ủy quyền đóng tài nguyên thành phần** (*delegated/composite closing*) — một kỹ thuật vẫn áp dụng trong Java hiện đại. Nó được xây dựng trên `AutoCloseable` và `try-with-resources`, vốn được giới thiệu từ Java 7.

Sau bài này, bạn sẽ:

1. Phân biệt **sở hữu tài nguyên** (*owned*) và **tham chiếu mượn** (*borrowed*); chỉ đóng tài nguyên theo đúng hợp đồng sở hữu.
2. Viết một composite có `close()` ủy quyền cho các resource thành phần.
3. Chọn thứ tự **đóng ngược thứ tự tạo/khai báo** khi có quan hệ phụ thuộc.
4. Tránh lỗi một `close()` ném exception khiến các thành phần phía sau **không được thử đóng**.
5. Dùng `try-with-resources` **ngay bên trong `close()`** để nhận được cơ chế đóng tất cả và giữ `suppressed exceptions`.
6. Hiểu **hai tầng suppressed exceptions** khi lỗi từ thân `try` của caller xảy ra đồng thời với nhiều lỗi khi composite đóng.
7. Tránh **đóng trùng**, thiết kế hành vi gọi `close()` nhiều lần khi phù hợp và dọn dẹp các resource đã mở nếu quá trình tạo composite thất bại.
8. Biên dịch và chạy các ví dụ trên **Java 17+**, đồng thời biết ranh giới cú pháp Java 7/Java 9.

**Nguyên tắc xuyên suốt:** Composite chịu trách nhiệm **đóng đúng những tài nguyên nó sở hữu**, cố gắng không bỏ sót thành phần khi một thao tác cleanup thất bại, và giữ đủ bằng chứng lỗi để caller quyết định xử lý.

## 2. `AutoCloseable` bảo đảm điều gì — và không bảo đảm điều gì?

Interface cốt lõi:

~~~java
public interface AutoCloseable {
    void close() throws Exception;
}
~~~

Đây là **chữ ký API rút gọn**, không phải file Java tự chạy. `close()` được gọi tự động khi đối tượng nằm trong phần khai báo resource của câu lệnh `try-with-resources`.

Những điểm cần phân biệt:

- **Có:** mỗi đối tượng `AutoCloseable` đã được đăng ký trong `try-with-resources` sẽ được Java cố gọi `close()` khi kết thúc phạm vi; việc đóng nhiều resource có quy tắc thứ tự và ghi nhận ngoại lệ rõ ràng.
- **Không:** JVM không dùng reflection để tự tìm mọi field của một composite và gọi `close()` trên chúng. Đóng thành phần là trách nhiệm của chính lớp composite hoặc contract wrapper tương ứng.
- **Không:** việc một resource triển khai `AutoCloseable` không tự xác định ai **sở hữu** nó. Caller hay composite phải thỏa thuận quyền đóng.
- **Không:** `AutoCloseable.close()` không bắt buộc *idempotent* theo đặc tả. Gọi hai lần có thể gây tác dụng phụ. Các implementation được **khuyến khích mạnh** làm cho việc đóng lặp an toàn khi phù hợp, nhưng không thể mặc định mọi thư viện đã làm như vậy.
- **Có phân biệt:** `java.io.Closeable` mở rộng `AutoCloseable`, có `close() throws IOException` và quy định việc đóng một resource đã đóng không có tác dụng. Không tự áp dụng bảo đảm hẹp hơn của `Closeable` cho mọi `AutoCloseable`.
- **Về checked exception:** interface gốc khai báo `throws Exception`; implementation có thể khai báo `throws IOException` hoặc không ném checked exception nếu hợp đồng thực tế cho phép. Chữ ký cụ thể giúp caller tránh phải bắt `Exception` quá rộng.
- **Khi close thất bại:** tài liệu `AutoCloseable` khuyến cáo implementation cố giải phóng tài nguyên và cập nhật trạng thái đóng **trước khi ném lỗi**, để giảm rủi ro lặp cleanup. Nhưng caller không được suy ra mọi resource chắc chắn đã giải phóng xong khi `close()` ném exception.
- **Không khuyến khích:** khai báo `close() throws InterruptedException`, vì lỗi bị suppressed có thể tương tác không mong muốn với trạng thái interrupt của thread. Hãy tuân theo hợp đồng của tài nguyên cụ thể, không áp dụng cách nuốt interrupt để tránh lỗi.

Nguồn chính thức: [AutoCloseable, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/AutoCloseable.html) và [Closeable, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Closeable.html).

## 3. Xác định quyền sở hữu trước khi viết `close()`

Một composite thường chứa nhiều field, nhưng **không phải field nào cũng là resource do composite sở hữu**.

| Thành phần | Composite có đóng không? | Căn cứ |
| --- | --- | --- |
| Resource được tạo **riêng cho composite** và sẽ không dùng độc lập bên ngoài | Thường **có** | Composite nhận trách nhiệm vòng đời |
| Resource được caller tạo rồi **chuyển giao ownership** cho composite theo API | **Có**, nếu hợp đồng nói rõ | Quyền đóng đã chuyển sang composite |
| Connection/stream do caller đưa vào để **mượn trong thời gian ngắn** | Thường **không** | Caller còn sử dụng và giữ trách nhiệm đóng |
| Wrapper mà `close()` đã đóng resource nền theo hợp đồng | Chỉ đóng qua một đường sở hữu phù hợp | Tránh đóng cùng resource hai lần |
| Field `String`, `Path` hoặc một giá trị cấu hình | **Không** | Không phải đối tượng đóng được |
| Một resource được **chia sẻ** cho nhiều composite | Cần hợp đồng ownership hoặc quản lý reference riêng | Không để mỗi composite tự ý đóng tài nguyên chung |

Có thể diễn đạt hợp đồng bằng hai kiểu API khác nhau:

~~~java
// Mô tả hai lựa chọn API, không phải class độc lập:
Composite useBorrowed(InputStream borrowed); // Không nhận quyền đóng.
Composite takeOwnership(InputStream owned);  // Nhận quyền đóng.
~~~

Tên phương thức chỉ là **minh họa**. Điều quan trọng là tài liệu API và code thực tế phải đồng nhất: “Ai được phép đóng? Khi nào? Có được dùng tiếp sau khi đóng composite không?”

**Không thể suy luận ownership từ việc field là `final`.** `final` chỉ chặn thay đổi tham chiếu của field; nó không nói đối tượng được sở hữu hay đi mượn. Tương tự, việc một đối tượng có method `close()` không đồng nghĩa composite luôn phải gọi method đó.

### 3.1. Quy tắc tránh *double-close*

Nếu `Composite.close()` đã đóng `child`, caller không nên khai báo **cả composite và child làm hai resource độc lập trong cùng một `try-with-resources`** trừ khi contract xác nhận thao tác đóng lặp an toàn và có chủ đích.

Đặc biệt với wrapper I/O, nhiều lớp sẽ **tự đóng tài nguyên nền** trong `close()`. Khi trường hợp đó được tài liệu wrapper xác nhận, thường chỉ đăng ký **wrapper ngoài cùng** trong `try-with-resources`, không đăng ký thêm tài nguyên nền một lần nữa. Ngược lại, nếu wrapper không sở hữu nguồn mà chỉ mượn, nó **không được tự đóng nguồn**.

## 4. Thứ tự đóng: nghĩ theo quan hệ phụ thuộc

Giả sử `base` là tài nguyên nền; `dependent` cần `base` còn hoạt động trong quá trình hoàn tất/đóng. Một thứ tự hợp lý là:

~~~text
Tạo hoặc mở:
    base  -> dependent

Sử dụng:
    dependent (dựa vào base)

Đóng:
    dependent -> base
~~~

Đây là **sơ đồ**, không phải cú pháp Java. Đóng theo thứ tự **ngược với tạo** giúp resource phụ thuộc hoàn tất công việc của nó trước khi resource nền biến mất.

Với `try-with-resources`, Java **khởi tạo từ trái sang phải** và **đóng từ phải sang trái**. Nếu một resource đóng lỗi, Java vẫn cố đóng các resource còn lại. Nếu đã có exception chính trước đó, lỗi đóng được lưu làm suppressed; nếu không, lỗi đóng đầu tiên có thể là primary và các lỗi đóng tiếp theo thành suppressed.

**Lưu ý:** “Đóng ngược thứ tự tạo” là lựa chọn thông dụng khi các resource có quan hệ phụ thuộc, không phải luật bắt buộc cho mọi mô hình. Nếu hai resource độc lập, thứ tự đôi khi không quan trọng; nếu một API quy định thứ tự đóng khác, phải theo hợp đồng API. Việc composite sở hữu các resource không tạo ra thứ tự đóng tự động nếu `close()` không hiện thực nó.

Nguồn: [JLS §14.20.3 — try-with-resources](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html#jls-14.20.3).

## 5. Ví dụ chạy được: composite ủy quyền đóng đúng thứ tự

Tạo file `DelegatingCompositeDemo.java`:

~~~java
public class DelegatingCompositeDemo {
    static final class Part implements AutoCloseable {
        private final String name;

        Part(String name) {
            this.name = name;
            System.out.println("open:" + name);
        }

        void use() {
            System.out.println("use:" + name);
        }

        @Override
        public void close() {
            System.out.println("close:" + name);
        }
    }

    static final class Composite implements AutoCloseable {
        private final Part base;
        private final Part dependent;
        private boolean closed;

        Composite(Part base, Part dependent) {
            this.base = base;
            this.dependent = dependent;
        }

        void use() {
            dependent.use();
        }

        @Override
        public void close() {
            if (closed) {
                return;
            }
            closed = true;

            try (Part first = base; Part second = dependent) {
                // Không cần thân: try-with-resources sẽ đóng các Part.
            }
        }
    }

    public static void main(String[] args) {
        Composite group = new Composite(
                new Part("base"),
                new Part("dependent"));

        try (group) {
            group.use();
        }

        group.close();
        System.out.println("after");
    }
}
~~~

~~~bash
javac --release 17 DelegatingCompositeDemo.java
java DelegatingCompositeDemo
~~~

Stdout chính xác:

~~~text
open:base
open:dependent
use:dependent
close:dependent
close:base
after
~~~

**Giải thích:**

1. `Composite` giữ hai field, với giả định constructor **nhận ownership** của chúng. Chính `Composite.close()` hiện thực ủy quyền đóng.
2. Trong `close()`, câu lệnh `try (Part first = base; Part second = dependent) { }` đăng ký hai child resource theo thứ tự `base` rồi `dependent`. **Thân trống vẫn hợp lệ**: mục đích chỉ là để Java đóng chúng đúng quy tắc.
3. Do ngữ nghĩa `try-with-resources`, `dependent` được đóng **trước** `base`. Không cần gọi thủ công `second.close(); first.close();` và tự viết lại logic suppression.
4. `try (group)` ở `main` khiến Java đóng composite một lần sau khi chạy `group.use()`.
5. Lời gọi `group.close()` **thứ hai** không tạo thêm dòng `close` vì lớp composite đã chủ động dùng cờ `closed`. Đây là chính sách **do class thiết kế**, không phải bảo đảm chung của `AutoCloseable`.
6. Cờ `closed` được đặt trước các lời gọi đóng con. Nếu việc đóng phát sinh lỗi, lời gọi tiếp theo không lặp lại thao tác tiềm ẩn tác dụng phụ. Điều này biểu thị **đã bắt đầu/đã cố đóng**, không khẳng định mọi resource chắc chắn đóng thành công.

**Về phiên bản:** Cú pháp khai báo resource trong header như `try (Part first = ...; Part second = ...)` có từ Java 7; riêng cú pháp **tham chiếu biến đã có** `try (group)` được mở rộng từ **Java 9**. Ví dụ này được biên dịch với Java 17; nếu làm việc ở source level Java 7/8, viết `try (Composite group = new Composite(...)) { ... }` và tổ chức vòng đời tương ứng.

**Về đa luồng:** cờ `boolean closed` trên đây chỉ minh họa chính sách cho luồng sử dụng tuần tự. Nếu nhiều thread có thể gọi `close()` đồng thời, cần xác định chính sách đồng bộ/atomic state và tránh race; `AutoCloseable` không tự tạo thread-safety.

## 6. Cách sai: dừng giữa chừng và bỏ sót tài nguyên còn lại

Đoạn triển khai ngây thơ rất dễ gặp:

~~~java
@Override
public void close() throws IOException {
    first.close();
    second.close();
}
~~~

Đây là **đoạn minh họa trong class**, giả sử hai field có method `close() throws IOException`. Nếu `first.close()` ném exception, dòng `second.close()` **không chạy**. Trong môi trường sản xuất, điều này có thể gây rò rỉ handle, socket hoặc trạng thái chưa giải phóng.

Chương trình tái hiện đầy đủ, file `NaiveCloseDemo.java`:

~~~java
import java.io.IOException;

public class NaiveCloseDemo {
    static final class Part implements AutoCloseable {
        final String name;
        final boolean fail;
        boolean closed;

        Part(String name, boolean fail) {
            this.name = name;
            this.fail = fail;
        }

        @Override
        public void close() throws IOException {
            closed = true;
            System.out.println("close:" + name);
            if (fail) {
                throw new IOException("fail:" + name);
            }
        }
    }

    static final class BadBundle implements AutoCloseable {
        final Part first = new Part("first", true);
        final Part second = new Part("second", false);

        @Override
        public void close() throws IOException {
            first.close();
            second.close();
        }
    }

    public static void main(String[] args) {
        BadBundle bundle = new BadBundle();

        try (bundle) {
            System.out.println("use");
        } catch (IOException ex) {
            System.out.println("caught:" + ex.getMessage());
        }

        System.out.println("secondClosed:" + bundle.second.closed);
    }
}
~~~

~~~bash
javac --release 17 NaiveCloseDemo.java
java NaiveCloseDemo
~~~

Stdout chính xác:

~~~text
use
close:first
caught:fail:first
secondClosed:false
~~~

**Vì sao?** `BadBundle.close()` chỉ là phương thức thông thường, không tự động có “cố đóng mọi field”. `first.close()` ném `IOException` khiến phương thức hoàn thành bất thường. Java chỉ biết đang phải gọi `BadBundle.close()`; nó **không biết** phải tự gọi tiếp `second.close()`.

Cờ `closed` trong chương trình chỉ minh họa việc **đã gọi** `close()` trên một thành phần, không chứng minh resource thực đã được hệ điều hành giải phóng thành công.

**Không sửa bằng cách nuốt exception:**

~~~java
try {
    first.close();
} catch (IOException ignored) {
    // Sai nếu không có chính sách ghi nhận/lan truyền.
}
second.close();
~~~

Đây là đoạn minh họa rủi ro, không phải cách triển khai đề xuất. Nó có thể giúp lời gọi thứ hai xảy ra, nhưng lại làm **mất thông tin** lỗi ở tài nguyên thứ nhất. Cần cơ chế ghi nhận cả lỗi đầu tiên lẫn những lỗi tiếp theo.

## 7. Cách đúng cho các resource đã sở hữu: dùng `try-with-resources` bên trong `close()`

Nếu composite có một nhóm child `AutoCloseable` đã được khởi tạo thành công, cách rõ ràng để **ủy quyền đóng nhiều child và giữ ngoại lệ** là dùng một câu lệnh `try-with-resources` trong chính `close()`.

Mẫu:

~~~java
@Override
public void close() throws IOException {
    try (Part firstResource = first;
         Part secondResource = second) {
        // Thân trống; chỉ mượn tên cục bộ để Java thực hiện cleanup.
    }
}
~~~

Đây là **đoạn minh họa bên trong class**, với `Part.close() throws IOException`. Quan trọng:

- `firstResource` và `secondResource` chỉ là **biến resource tham chiếu cùng đối tượng child đã có**, không tạo bản sao và không mở lại child.
- Vì là **khai báo resource mới với initializer**, cú pháp này dùng được từ **Java 7**.
- Java đóng `secondResource` trước rồi `firstResource`, kể cả khi một lần đóng ném exception.
- Nếu cả hai đóng lỗi, lần đóng thất bại đầu tiên là primary; lần đóng sau sẽ thành suppressed.
- Trong một composite thật, cần phối hợp chính sách gọi `close()` một lần, các thành phần được sở hữu và không đóng trùng ở caller.

### 7.1. Ví dụ chương trình khi hai child đều đóng lỗi

Tạo file `RobustCloseDemo.java`:

~~~java
import java.io.IOException;

public class RobustCloseDemo {
    static final class Part implements AutoCloseable {
        final String name;

        Part(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close:" + name);
            throw new IOException("fail:" + name);
        }
    }

    static final class Bundle implements AutoCloseable {
        final Part first = new Part("first");
        final Part second = new Part("second");
        boolean closed;

        @Override
        public void close() throws IOException {
            if (closed) {
                return;
            }
            closed = true;
            try (Part one = first; Part two = second) {
            }
        }
    }

    public static void main(String[] args) throws IOException {
        Bundle bundle = new Bundle();

        try (bundle) {
            System.out.println("use");
        } catch (IOException ex) {
            System.out.println("primary:" + ex.getMessage());
            for (Throwable other : ex.getSuppressed()) {
                System.out.println("suppressed:" + other.getMessage());
            }
        }

        bundle.close();
        System.out.println("repeat:ok");
    }
}
~~~

~~~bash
javac --release 17 RobustCloseDemo.java
java RobustCloseDemo
~~~

Stdout chính xác:

~~~text
use
close:second
close:first
primary:fail:second
suppressed:fail:first
repeat:ok
~~~

**Điểm học chính:**

1. Cả `second.close()` và `first.close()` đều được **gọi**, bất chấp lỗi ở tài nguyên thứ hai.
2. Thứ tự là **second → first**, do cú pháp tài nguyên trong header.
3. Khi thân `try` phía trong `close()` trống và không lỗi, exception từ `second.close()` là **primary** của lần ủy quyền đóng; `first.close()` thành **suppressed** trên primary đó.
4. Caller đọc suppressed qua `ex.getSuppressed()` để không mất lỗi còn lại.
5. Lời gọi `bundle.close()` lần hai không thực thi lại child close vì cờ `closed` của chính `Bundle`.
6. Dòng `repeat:ok` chỉ cho thấy **không ném lỗi trong lần close thứ hai** theo chính sách code mẫu; nó **không chứng minh lần đóng đầu đã thành công**, bởi hai child đã ném `IOException`.

**Vì sao không tự dùng `try/finally` thủ công?** Có thể tự viết logic tương đương, nhưng việc gộp ngoại lệ đúng cách đòi hỏi cân nhắc cả lỗi thân/khởi tạo và nhiều lỗi close. Cú pháp `try-with-resources` đã có hợp đồng ngôn ngữ cho các trường hợp đó; dùng nó bên trong `close()` vừa ngắn hơn vừa khó bỏ sót hơn.

## 8. Hai tầng suppressed exceptions: lỗi của caller và lỗi của composite

Một tình huống quan trọng với ủy quyền đóng: **thân `try` của caller bị lỗi** và **nhiều resource con của composite cũng đóng lỗi**.

Khi composite đóng các thành phần bằng `try-with-resources` bên trong `close()`, phần đóng bên trong có thể tạo **một exception primary của thao tác composite.close()`** và đính kèm các lỗi đóng khác vào nó. Sau đó, vì **thân `try` ngoài** đã có lỗi, toàn bộ exception do `composite.close()` ném ra sẽ bị **suppressed vào lỗi từ thân bên ngoài**.

Vì vậy, danh sách suppressed có thể **lồng nhau**:

~~~text
IllegalArgumentException("work")          <- primary của caller
└── suppressed[0]: IOException("close:second") <- primary của composite.close()
    └── suppressed[0]: IOException("close:first") <- lỗi child tiếp theo
~~~

Đây là **sơ đồ**, không phải Java source. Không tự cho rằng cả hai lỗi đóng con sẽ nằm trực tiếp cùng cấp trong `outer.getSuppressed()`.

### 8.1. Ví dụ chạy được

Tạo file `NestedSuppressedDemo.java`:

~~~java
import java.io.IOException;

public class NestedSuppressedDemo {
    static final class Part implements AutoCloseable {
        final String name;

        Part(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close:" + name);
            throw new IOException("close:" + name);
        }
    }

    static final class Bundle implements AutoCloseable {
        final Part first = new Part("first");
        final Part second = new Part("second");

        @Override
        public void close() throws IOException {
            try (Part one = first; Part two = second) {
            }
        }
    }

    public static void main(String[] args) {
        try (Bundle bundle = new Bundle()) {
            throw new IllegalArgumentException("work");
        } catch (Exception ex) {
            System.out.println("primary:" + ex.getMessage());
            System.out.println("outerSuppressed:" + ex.getSuppressed().length);

            Throwable closeError = ex.getSuppressed()[0];
            System.out.println("closePrimary:" + closeError.getMessage());
            System.out.println(
                    "innerSuppressed:" +
                    closeError.getSuppressed()[0].getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 NestedSuppressedDemo.java
java NestedSuppressedDemo
~~~

Stdout chính xác:

~~~text
close:second
close:first
primary:work
outerSuppressed:1
closePrimary:close:second
innerSuppressed:close:first
~~~

Phân tích:

- Ở tầng ngoài, `IllegalArgumentException("work")` từ thân `try` là primary.
- Trong `Bundle.close()`, `second.close()` ném lỗi rồi `first.close()` ném lỗi; lần đóng bên trong tạo một `IOException("close:second")` làm primary của **lần đóng composite**, có suppressed là `IOException("close:first")`.
- Khi `Bundle.close()` ném exception trên ra ngoài, `try-with-resources` ở caller **đính kèm exception ấy** vào primary `IllegalArgumentException("work")`.
- `outer.getSuppressed().length` bằng **1**, không phải 2. Muốn thấy lỗi đóng `first` phải xem `outer.getSuppressed()[0].getSuppressed()`.

Ví dụ dùng `getSuppressed()[0]` vì đã biết chắc chương trình tạo các lỗi đó. Trong chương trình xử lý dữ liệu thực, phải **kiểm tra độ dài mảng trước khi truy cập**, vì không phải trường hợp nào cũng có suppressed.

**Kinh nghiệm logging:** Khi truyền `Throwable` gốc cho logger có formatter hỗ trợ, hãy xác nhận stack trace, cause và các tầng suppressed đều được giữ. Nếu chỉ log `getMessage()`, toàn bộ lịch sử dọn dẹp có thể bị mất.

## 9. Tài nguyên được mượn: không ủy quyền đóng thay caller

Tạo file `OwnershipDemo.java`:

~~~java
public class OwnershipDemo {
    static final class Part implements AutoCloseable {
        final String name;
        boolean closed;

        Part(String name) {
            this.name = name;
        }

        @Override
        public void close() {
            closed = true;
            System.out.println("close:" + name);
        }
    }

    static final class Bundle implements AutoCloseable {
        final Part borrowed;
        final Part owned;

        Bundle(Part borrowed, Part owned) {
            this.borrowed = borrowed;
            this.owned = owned;
        }

        @Override
        public void close() {
            owned.close();
        }
    }

    public static void main(String[] args) {
        try (Part external = new Part("external")) {
            try (Bundle bundle =
                    new Bundle(external, new Part("owned"))) {
                System.out.println("use");
            }
            System.out.println("externalOpen:" + !external.closed);
        }
    }
}
~~~

~~~bash
javac --release 17 OwnershipDemo.java
java OwnershipDemo
~~~

Stdout chính xác:

~~~text
use
close:owned
externalOpen:true
close:external
~~~

Chú ý hai vòng đời:

1. `external` được **caller** mở và đặt trong `try-with-resources` ngoài.
2. `Bundle` chỉ **mượn** `external`, nhưng **sở hữu** resource `owned` của riêng nó.
3. Khi `Bundle.close()` chạy, nó chỉ đóng `owned`. `external` vẫn mở ở thời điểm in `externalOpen:true`.
4. Khi rời `try-with-resources` ngoài, caller mới đóng `external`.

**Đây là hợp đồng giả định minh họa:** không phải mọi constructor nhận `AutoCloseable` đều mượn tham chiếu. Trong code production, tài liệu API phải nói rõ có chuyển quyền sở hữu hay không. Nếu composite nhận ownership của `external`, nó phải đóng `external` và caller **không nên tiếp tục coi mình còn quyền sử dụng/đóng** resource đó.

**Với tài nguyên chia sẻ:** tránh áp dụng cách “mọi consumer tự đóng khi xong” nếu vẫn có consumer khác cần nó. Một owner cấp cao hơn có thể quản lý vòng đời chung; cơ chế reference counting/pool phải bám vào hợp đồng của thư viện, không tự suy diễn từ `AutoCloseable`.

## 10. Lỗi đóng trùng khi cả wrapper lẫn child cùng đăng ký trong `try`

Tạo file `DoubleClosePitfallDemo.java`:

~~~java
public class DoubleClosePitfallDemo {
    static final class Part implements AutoCloseable {
        int calls;

        @Override
        public void close() {
            calls++;
            System.out.println("partClose:" + calls);
        }
    }

    static final class Wrapper implements AutoCloseable {
        final Part child;

        Wrapper(Part child) {
            this.child = child;
        }

        @Override
        public void close() {
            child.close();
        }
    }

    public static void main(String[] args) {
        try (Part part = new Part();
             Wrapper wrapper = new Wrapper(part)) {
            System.out.println("work");
        }
    }
}
~~~

~~~bash
javac --release 17 DoubleClosePitfallDemo.java
java DoubleClosePitfallDemo
~~~

Stdout chính xác:

~~~text
work
partClose:1
partClose:2
~~~

**Vì sao child đóng hai lần?**

- Java đăng ký **hai resource** trong header `try`: `part` và `wrapper`.
- Khi thoát `try`, Java đóng **wrapper trước**. `Wrapper.close()` tự gọi `part.close()`: lần **1**.
- Sau đó Java tiếp tục đóng resource `part` đã đăng ký độc lập: lần **2**.

Đây là ví dụ **cố ý minh họa lỗi thiết kế sở hữu**. Vì `AutoCloseable.close()` **không bắt buộc idempotent**, không thể giả định lần gọi thứ hai vô hại với resource tự viết hoặc thư viện bên thứ ba.

**Cách sửa:** Nếu `wrapper` **sở hữu và đóng** `part`, chỉ đăng ký `wrapper` làm resource của phạm vi bên ngoài, chẳng hạn:

~~~java
try (Wrapper wrapper = new Wrapper(new Part())) {
    System.out.println("work");
}
~~~

Đây là đoạn chạy được khi đặt vào `main` của class mẫu phía trên, nhưng **không phải file độc lập**. Nó giả định `Wrapper.close()` đóng child và quyền sở hữu đã chuyển sang wrapper. Nếu wrapper **chỉ mượn** child, phải sửa hợp đồng của wrapper theo hướng không tự đóng child, thay vì bỏ quản lý vòng đời child.

**Không chỉ dựa vào idempotence để chữa quyền sở hữu sai.** Cho dù `Closeable.close()` có quy tắc đóng lặp, việc một resource bị đóng sớm vẫn có thể khiến consumer khác đang sử dụng bị lỗi.

## 11. Khởi tạo composite thất bại: dọn phần đã mở trước khi chuyển quyền sở hữu

Rủi ro xảy ra **trước cả khi composite được tạo thành công**. Ví dụ factory định tạo hai thành phần rồi trả về một `Bundle`. Nó đã mở resource thứ nhất, nhưng mở resource thứ hai bị lỗi. Chưa có `Bundle` nào được trả về để caller đặt vào `try-with-resources`, nên **factory phải dọn tài nguyên đã mở trước đó**.

Chương trình `FactoryFailureDemo.java`:

~~~java
import java.io.IOException;

public class FactoryFailureDemo {
    static final class Part implements AutoCloseable {
        final String name;

        Part(String name) {
            this.name = name;
            System.out.println("open:" + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("close:" + name);
            throw new IOException("close-failed:" + name);
        }
    }

    static final class Bundle implements AutoCloseable {
        final Part first;
        final Part second;

        Bundle(Part first, Part second) {
            this.first = first;
            this.second = second;
        }

        @Override
        public void close() throws IOException {
            try (Part one = first; Part two = second) {
            }
        }
    }

    static Part openSecond() throws IOException {
        System.out.println("open:second-attempt");
        throw new IOException("open-failed:second");
    }

    static Bundle create() throws IOException {
        Part first = new Part("first");

        try {
            Part second = openSecond();
            return new Bundle(first, second);
        } catch (IOException ex) {
            try {
                first.close();
            } catch (IOException cleanup) {
                ex.addSuppressed(cleanup);
            }
            throw ex;
        }
    }

    public static void main(String[] args) {
        try (Bundle bundle = create()) {
            System.out.println("work");
        } catch (IOException ex) {
            System.out.println("primary:" + ex.getMessage());
            for (Throwable other : ex.getSuppressed()) {
                System.out.println("suppressed:" + other.getMessage());
            }
        }
    }
}
~~~

~~~bash
javac --release 17 FactoryFailureDemo.java
java FactoryFailureDemo
~~~

Stdout chính xác:

~~~text
open:first
open:second-attempt
close:first
primary:open-failed:second
suppressed:close-failed:first
~~~

Giải thích:

- `create()` tạo resource `first` thành công, sau đó `openSecond()` ném `IOException`.
- Vì factory chưa trả `Bundle`, **`try (Bundle bundle = create())` ở caller không có Bundle đã khởi tạo thành công để đóng**.
- Factory tự gọi `first.close()` trong nhánh xử lý lỗi khởi tạo. Lời gọi ấy cũng lỗi, nên factory giữ exception mở thứ hai làm **primary**, dùng `ex.addSuppressed(cleanup)` để không mất lỗi dọn resource thứ nhất.
- Lệnh `System.out.println("work")` không chạy vì resource initializer ở caller đã thất bại.
- Caller có thể đọc cả lỗi mở và lỗi cleanup mà không cần đoán từ stdout.

**Giới hạn quan trọng của chương trình mẫu:** nhánh `catch (IOException)` chỉ quản lý đường lỗi checked `IOException` mà factory này tạo ra. Một factory thực tế phải định nghĩa hợp đồng cho **các đường lỗi khác**, bao gồm `RuntimeException`/lỗi từ constructor/khâu chuyển giao ownership, và bảo đảm cleanup tương ứng. Không sao chép mẫu này rồi coi như đã xử lý mọi `Throwable`. Khi quá trình khởi tạo phức tạp, cần tổ chức rõ *ownership transfer*: chỉ chuyển quyền cho composite sau khi các phần cần thiết đã mở thành công.

Một lỗi ngược lại cũng cần tránh: đặt `first` trong `try-with-resources` của factory rồi **trả `Bundle` đang giữ `first`** ở bên trong phạm vi đó. Khi factory `return`, `first` sẽ bị đóng trước khi caller kịp dùng Bundle. Để chuyển ownership thành công, resource phải **tiếp tục sống** sau khi factory trả kết quả; chỉ dọn resource chưa chuyển giao khi quá trình tạo bị lỗi.

## 12. Thực hiện ủy quyền với danh sách resource có số lượng động

Với vài field cố định, dùng `try-with-resources` trong `close()` như mục 7 là đơn giản nhất. Với một nhóm có số lượng resource thay đổi theo runtime, cấu trúc thông thường là một danh sách/stack chứa **các resource được sở hữu** theo thứ tự đã thêm.

### 12.1. Các quyết định cần chốt trước khi viết vòng lặp

1. **Ai đăng ký tài nguyên?** Chỉ resource được chuyển quyền sở hữu cho composite mới được thêm vào nhóm cần đóng.
2. **Thứ tự đóng?** Nếu tài nguyên mở theo thứ tự `A, B, C` và resource sau có thể phụ thuộc resource trước, đóng theo `C, B, A`.
3. **Khi một `close()` lỗi?** Không để exception đầu tiên làm mất cơ hội đóng các resource còn lại.
4. **Giữ lỗi thế nào?** Giữ lỗi đầu tiên của thao tác đóng làm primary, thêm các lỗi đóng tiếp theo dưới dạng suppressed (hoặc dùng một exception tổng hợp với hợp đồng được thiết kế rõ).
5. **Chấp nhận kiểu ngoại lệ nào?** `AutoCloseable.close()` có thể ném `Exception`, và cũng có thể xảy ra unchecked exception/`Error`. Viết helper tổng quát phải tuân theo chính sách xử lý/lan truyền rõ ràng; không bắt rồi nuốt `Throwable` hàng loạt.
6. **Có tài nguyên trùng identity không?** Nếu cùng một object được đăng ký hai lần, vòng đóng ngược có thể gọi `close()` hai lần trên cùng object. Giữ ownership một lần hoặc có cơ chế kiểm tra trùng khi cần.
7. **Có nhiều thread thao tác đồng thời không?** Đồng bộ hoạt động đăng ký, sử dụng và đóng theo hợp đồng của composite, tránh thêm resource khi composite đã bước vào trạng thái closing/closed.

### 12.2. Phác thảo logic và giới hạn

~~~text
close():
    chỉ bắt đầu một lần, không đăng ký thêm resource mới
    lỗiĐầuTiên = chưa có

    duyệt các resource thuộc ownership theo thứ tự ngược:
        thử gọi resource.close()
        nếu lỗi và lỗiĐầuTiên chưa có:
            ghi lại lỗi hiện tại là lỗiĐầuTiên
        nếu lỗi và đã có lỗiĐầuTiên:
            thêm lỗi hiện tại vào danh sách suppressed thích hợp

    sau khi đã thử đóng toàn bộ:
        nếu có lỗiĐầuTiên, lan truyền theo hợp đồng
~~~

Đây là **pseudocode**, không phải Java tự chạy. Nó diễn tả ý tưởng tổng hợp lỗi, **không phải** triển khai đầy đủ cho mọi loại `Throwable`, chính sách thread interruption hoặc trạng thái tài nguyên. Nếu thật sự cần đóng một tập resource động lớn, hãy viết hàm/class chuyên trách được kiểm thử toàn bộ failure paths; khi có thể biểu diễn bằng tài nguyên lồng nhau hoặc những phạm vi `try-with-resources` tĩnh, ưu tiên cơ chế ngôn ngữ để giảm rủi ro.

**Không nên đưa một `List<AutoCloseable>` vào ngoặc `try` với kỳ vọng JVM tự đóng mọi phần tử.** Bản thân `List` không triển khai `AutoCloseable`, và Java chỉ đóng resource được khai báo trong header, không tự động đóng collection contents.

### 12.3. Khi nên tránh tạo composite

Nếu code chỉ cần dùng hai resource cùng phạm vi mà không cần tạo một đối tượng sống độc lập, khai báo trực tiếp chúng trong cùng `try-with-resources`:

~~~java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {
    in.transferTo(out);
}
~~~

Đây là **đoạn minh họa Java 17+ trong phương thức**, với `source`/`target` kiểu `Path` và các import phù hợp. `InputStream.transferTo` là API từ Java 9. Java sẽ đóng `out` rồi `in` và giữ suppressed exceptions đúng theo JLS — **không cần một composite chỉ để làm trung gian**.

Chọn composite khi bạn thật sự muốn tạo **một đơn vị quản lý vòng đời** có API riêng, chứa logic phối hợp, hoặc chuyển giao ownership qua một ranh giới module. Không thêm abstraction chỉ vì có thể implement `AutoCloseable`.

## 13. Các quy tắc bổ sung khi thiết kế `close()` cho composite

### 13.1. Idempotence là chính sách của implementation

API `AutoCloseable` **không bắt buộc** `close()` idempotent; đối với composite tự viết, nên cân nhắc cờ trạng thái/đồng bộ để tránh đóng child lặp. Tuy vậy, cờ `closed=true` không tự động giải quyết mọi vấn đề:

- Nếu set cờ **sau** các lệnh `close()` và một child ném exception, lần gọi tiếp theo có thể thử đóng lại child đã được đóng một phần.
- Nếu set cờ **trước**, lần gọi tiếp theo không lặp lại, nhưng cũng không có nghĩa mọi child đã giải phóng thành công.
- Nếu có nhiều thread, một `boolean` thông thường chưa đủ để bảo đảm hành vi đóng đúng một lần và không chạy đồng thời.
- Một số resource yêu cầu chính sách retry/recovery đặc biệt; đừng tự quyết định retry khi API không cho phép.

Phân biệt trạng thái **“đã bắt đầu đóng/đã cố đóng”** với **“đã đóng thành công toàn bộ”**. Có thể cần hai trạng thái nếu lớp thực sự phải công khai tính sẵn sàng sau lỗi.

### 13.2. Ghi nhận exception đúng cây, không tự ý flatten

Khi composite đang đóng child, exception từ child có thể đã có cause và suppressed của riêng nó. Nếu đóng composite lại lỗi khi caller đã có primary, cả **cụm lỗi** có thể nằm trong một suppressed exception ở tầng ngoài, giống ví dụ `NestedSuppressedDemo`.

- Đừng chỉ lấy `getSuppressed()[0]` và kết luận chỉ có một lỗi cleanup.
- Đừng chỉ log exception message rồi bỏ stack trace.
- Đừng chuyển mọi suppressed exception thành cause, vì cause mô tả quan hệ nguyên nhân khác.
- Đừng cố bảo đảm có suppression ở mọi exception: `Throwable` có khả năng được khởi tạo với suppression disabled.
- Khi cần kiểm tra cây lỗi tùy chỉnh, đề phòng tham chiếu vòng/các exception dùng lại; dùng logging framework đáng tin hoặc cấu trúc duyệt có đánh dấu identity.

### 13.3. Kiểu resource và chữ ký `throws`

Ví dụ:

~~~java
@Override
public void close() throws IOException {
    try (InputStream inputToClose = input;
         OutputStream outputToClose = output) {
    }
}
~~~

Đây là **đoạn phương thức minh họa** trong class có hai field `input`/`output`; chúng phải là tài nguyên mà composite sở hữu. Vì `InputStream.close()` và `OutputStream.close()` có hợp đồng `IOException`, `close() throws IOException` là lựa chọn phù hợp.

Nếu khai báo tất cả child dưới kiểu tổng quát `AutoCloseable`, compiler có thể yêu cầu xử lý/khai báo `Exception` do chữ ký `AutoCloseable.close()`. Ưu tiên giữ **kiểu cụ thể** hoặc một interface miền nghiệp vụ có checked exception hẹp nếu phù hợp. Không chặn mọi exception một cách cơ học chỉ để làm code biên dịch.

### 13.4. Công việc phải hoàn tất trước khi đóng

Với resource có hành vi **flush/commit/rollback** trong hoặc trước `close()`, cần đọc hợp đồng từng API. Không khẳng định mọi lời gọi `close()` tương đương commit hay chắc chắn lưu dữ liệu. Ví dụ một transaction có thể phải `commit()` rõ ràng; khi thất bại cần rollback theo contract, trong khi đóng connection không tự bảo đảm đã commit. Đóng composite nên **dọn tài nguyên**, còn việc xác nhận thành công nghiệp vụ phải được thiết kế riêng khi cần.

Với stream wrapper, một lớp có thể sở hữu và đóng stream nền, lớp khác có thể chỉ mượn. Xem JavaDoc của chính wrapper đang dùng; không mặc định tất cả triển khai `AutoCloseable` có cùng ngữ nghĩa.

## 14. Bảng kiểm tra nhanh khi review pull request

| Câu hỏi | Dấu hiệu ổn | Dấu hiệu cần sửa |
| --- | --- | --- |
| Ai sở hữu các child? | Hợp đồng constructor/factory ghi rõ ownership | Chỉ thấy field là đoán phải đóng |
| Caller đóng gì? | Chỉ đăng ký resource tại đúng owner boundary | Caller đăng ký cả child lẫn wrapper sở hữu child |
| Child được đóng theo thứ tự nào? | Thứ tự rõ, phù hợp quan hệ phụ thuộc | Đóng base trước dependent dù dependent cần base lúc close |
| Một child `close()` lỗi? | Child còn lại vẫn được **cố đóng** | Lệnh đóng tuần tự đơn giản bị exception đầu tiên ngắt |
| Có mất thông tin lỗi? | Primary, suppressed, cause được giữ | Nuốt lỗi trong `catch (Exception ignored)` |
| Tình huống thân caller lỗi? | Cây suppressed ngoài/trong được hiểu | Chỉ kiểm tra `outer.getSuppressed().length` và bỏ các tầng con |
| Factory mở dở bị lỗi? | Có cleanup cho tài nguyên đã mở và chưa transfer ownership | Chưa trả composite nên resource bị rò rỉ |
| Gọi `close()` hai lần? | Có hợp đồng rõ, tránh tác dụng phụ bất ngờ | Mặc định mọi `AutoCloseable` idempotent |
| Có sử dụng sau khi đóng? | API bảo vệ trạng thái đóng nếu cần | Còn cho phép thao tác trên child đã close |
| Có race với đóng ở thread khác? | Vòng đời/đăng ký resource được đồng bộ theo thiết kế | Cờ `boolean closed` bị xem là thread-safe mặc định |
| Có quá nhiều resource động? | Có chiến lược đảo thứ tự và aggregate lỗi đã test | `List<AutoCloseable>` được kỳ vọng auto-close nội dung |
| Kiểu `throws` phù hợp? | Dùng ngoại lệ đủ cụ thể, không che bug | Luôn `catch (Exception)` rồi bỏ qua để qua compiler |

## 15. Câu hỏi tự kiểm tra

**1.** Nếu một class `Bundle implements AutoCloseable` chứa hai field kiểu `AutoCloseable`, Java có tự gọi `close()` trên cả hai field khi đóng Bundle không?  
**Đáp án:** Không. Java chỉ gọi `Bundle.close()`; implementation của Bundle phải ủy quyền đóng các child do mình sở hữu.

**2.** Tài nguyên `base` được mở trước và `dependent` cần base trong lúc đóng. Thứ tự đóng nên là gì?  
**Đáp án:** Thường đóng `dependent` trước, rồi `base`. `try-with-resources` đăng ký `base` trước `dependent` sẽ tự đóng theo thứ tự ngược.

**3.** Tại sao `first.close(); second.close();` dễ gây rò rỉ?  
**Đáp án:** Nếu `first.close()` ném exception, `second.close()` không được gọi, trừ khi có cơ chế cleanup/aggregate lỗi khác.

**4.** Có thể dùng `try (Part a = first; Part b = second) { }` ngay bên trong `Composite.close()` không?  
**Đáp án:** Có, nếu các biến là resource hợp lệ và composite có quyền sở hữu chúng. Java sẽ cố đóng `b` rồi `a`, giữ lỗi theo ngữ nghĩa `try-with-resources`.

**5.** `try (existingBundle)` có được dùng khi target source level là Java 7?  
**Đáp án:** Không. Dùng biến resource đã tồn tại trực tiếp trong ngoặc `try` là khả năng từ Java 9. Dạng khai báo có initializer `try (Bundle bundle = create())` có từ Java 7.

**6.** Caller đưa một resource dùng chung vào composite nhưng chỉ cho mượn. Composite có được tự đóng nó khi kết thúc không?  
**Đáp án:** Không, nếu hợp đồng là borrowed. Owner thực sự phải quản lý vòng đời; composite chỉ đóng tài nguyên mà nó sở hữu.

**7.** Trong `try (Part child = ...; Wrapper wrapper = new Wrapper(child))`, nếu `wrapper.close()` cũng đóng `child`, có thể xảy ra gì?  
**Đáp án:** Child có thể bị gọi `close()` hai lần: một lần từ wrapper, một lần từ `try-with-resources`. Không mặc định an toàn với mọi `AutoCloseable`.

**8.** Lỗi từ thân `try` của caller và hai lỗi đóng child của composite đều xảy ra. Cả hai lỗi child có nhất thiết nằm trực tiếp trong `callerException.getSuppressed()` không?  
**Đáp án:** Không. Composite có thể tạo một exception đóng làm primary và một suppressed phía trong; cả exception đóng composite được suppressed vào lỗi thân của caller. Cần đọc nhiều tầng.

**9.** Factory mở child A thành công, mở child B lỗi trước khi trả composite. Caller đã dùng `try (Bundle bundle = factory())`; JVM có tự biết đóng A không?  
**Đáp án:** Không, nếu A chưa được resource header tương ứng quản lý và chưa có Bundle trả về. Factory phải cleanup resource đã mở nhưng chưa chuyển giao ownership.

**10.** Vì sao cờ `closed=true` nên được cân nhắc trước khi ủy quyền đóng?  
**Đáp án:** Tránh lần gọi close tiếp theo vô tình lặp lại thao tác trên resource đã được cố đóng khi child close ném exception. Nhưng cờ này không bảo đảm tất cả child đóng thành công hoặc thread-safe.

**11.** Dùng `Closeable` khác `AutoCloseable` về idempotence và loại exception như thế nào?  
**Đáp án:** `Closeable.close()` khai báo `IOException` và có yêu cầu đóng resource đã đóng không có tác dụng; `AutoCloseable.close()` có chữ ký rộng hơn `throws Exception` và không bắt buộc idempotent.

**12.** Có nên tạo composite khi chỉ cần mở hai file cùng một phạm vi ngắn?  
**Đáp án:** Không bắt buộc. Nếu không cần một đơn vị vòng đời độc lập, đặt trực tiếp cả hai resource vào `try-with-resources` sẽ đơn giản hơn và đã có cơ chế đóng/giữ lỗi của Java.

## 16. Nguồn chính thức đang áp dụng

- [Java SE 26 — `AutoCloseable` API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng `close()`, ngoại lệ, lời khuyên về trạng thái đóng, idempotence và lưu ý `InterruptedException`.
- [Java SE 26 — `Closeable` API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Closeable.html): yêu cầu idempotence và chữ ký `throws IOException` của `Closeable.close()`.
- [Java SE 26 JLS §14.20.3 — try-with-resources](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html#jls-14.20.3): mở trái–phải, đóng phải–trái, xử lý initializer failure và các exception phát sinh khi đóng.
- [Java SE 26 JLS §14.20.3.1 — Basic try-with-resources](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html#jls-14.20.3.1): quy tắc chính xác của primary và suppressed trong các phạm vi resource lồng nhau.
- [Java SE 26 API — `Throwable.getSuppressed()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Throwable.html#getSuppressed()): đọc những lỗi giữ lại, có thể nằm ở nhiều tầng khi composite đóng.
- [Java SE 26 API — `Throwable.addSuppressed(Throwable)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Throwable.html#addSuppressed(java.lang.Throwable)): bổ sung lỗi cleanup trong factory hoặc lớp đóng được hiện thực thủ công.
- [Java SE 7 JLS §14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se7/html/jls-14.html#jls-14.20.3): xác nhận ngữ nghĩa cơ bản của việc đóng tài nguyên từ Java 7.
- [JEP 213 — Milling Project Coin](https://openjdk.org/jeps/213): nguồn về cải tiến `try (existingVariable)` từ Java 9, phân biệt với khai báo resource Java 7.
- [Java SE 26 API — `InputStream`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/InputStream.html): ví dụ API dùng với `try-with-resources`; muốn biết wrapper có đóng stream nền hay không, đọc hợp đồng class cụ thể.

**Ghi nhớ:** *Ủy quyền đóng* không có nghĩa “gọi `close()` trên mọi field”. Hãy đóng **đúng tài nguyên thuộc ownership**, theo **thứ tự phù hợp phụ thuộc**, **thử đóng tiếp dù một child lỗi**, và **giữ lỗi bằng suppressed exceptions**. Trong Java hiện đại, với nhóm resource cố định, một `try-with-resources` bên trong `Composite.close()` thường là công cụ ngắn gọn và an toàn nhất để hiện thực những quy tắc đó.