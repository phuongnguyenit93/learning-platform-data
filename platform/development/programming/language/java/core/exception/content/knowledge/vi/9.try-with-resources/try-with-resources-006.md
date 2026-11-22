# Thứ tự đóng tài nguyên ngược với thứ tự tạo trong Java try-with-resources

Khi sử dụng **try-with-resources**, Java tự gọi `close()` cho những tài nguyên đã được khởi tạo thành công khi rời vùng `try`. Nếu khai báo nhiều tài nguyên trong cùng một phần đầu `try (...)`, Java **khởi tạo từ trái sang phải nhưng đóng theo chiều ngược lại: từ phải sang trái**. Đây là quy tắc quan trọng để quản lý các lớp tài nguyên phụ thuộc lẫn nhau và để dự đoán kết quả khi có ngoại lệ.

~~~java
try (Resource a = openA();
     Resource b = openB();
     Resource c = openC()) {
    use(a, b, c);
}
~~~

Đoạn trên là **mã giả theo cú pháp Java**, trong đó `Resource` cần là lớp triển khai `AutoCloseable` và các hàm `openA`, `openB`, `openC`, `use` phải tồn tại. Khi mọi thao tác đều thành công:

~~~text
Khởi tạo: A -> B -> C
Sử dụng:  thân try
Đóng:     C -> B -> A
~~~

Không phải JVM “đóng tất cả cùng lúc” hay theo thứ tự ngẫu nhiên; đối với các tài nguyên khai báo theo thứ tự trong cùng một try-with-resources, thứ tự đóng được Java xác định rõ. Quy tắc này vẫn áp dụng nếu thân `try` chạy xong bình thường, `return` hoặc ném ngoại lệ — miễn là luồng Java còn thực hiện được việc rời cấu trúc `try`.

## 1. Vì sao cần đóng theo thứ tự ngược?

Trong hệ thống thực, tài nguyên thường được **xây dựng theo tầng**: tài nguyên sau sử dụng hoặc bao bọc tài nguyên trước.

Ví dụ trực quan:

~~~text
Mở luồng dữ liệu gốc InputStream
         |
Tạo InputStreamReader đọc từ luồng gốc
         |
Tạo BufferedReader đọc từ InputStreamReader
         |
      Sử dụng
         |
Đóng BufferedReader
         |
Đóng lớp reader bên dưới / luồng gốc theo cơ chế đóng liên quan
~~~

Khi quản lý một chuỗi đối tượng, đóng tầng ngoài trước có thể bảo đảm nó thực hiện nốt thao tác cuối cùng và không còn sử dụng tầng dưới sau khi tầng dưới đã đóng.

Không được suy ra rằng **mọi đối tượng độc lập có quan hệ phụ thuộc** chỉ vì chúng được khai báo cạnh nhau. Thứ tự ngược là **quy tắc của ngôn ngữ**, còn lý do tạo tài nguyên theo thứ tự nào phụ thuộc thiết kế của ứng dụng.

Đóng theo chiều ngược thường được gọi là **LIFO** (*last in, first out*): đối tượng khởi tạo sau cùng được đóng trước tiên. Với ba tài nguyên `A, B, C` trong cùng danh sách, thứ tự là:

| Giai đoạn | Thứ tự |
| --- | --- |
| Đánh giá và khởi tạo tài nguyên | `A`, rồi `B`, rồi `C` |
| Chạy phần thân `try` | Khi tất cả tài nguyên cần thiết đã được khởi tạo thành công |
| Gọi `close()` | `C`, rồi `B`, rồi `A` |

Không nên nhầm quy tắc này với thứ tự hủy đối tượng của garbage collector. Try-with-resources gọi `close()` theo luồng chương trình; nó **không** đợi garbage collector phát hiện đối tượng không còn được tham chiếu.

## 2. Điều kiện để một đối tượng dùng được trong try-with-resources

Tài nguyên phải thuộc kiểu có thể chuyển thành `java.lang.AutoCloseable`. Giao diện cốt lõi có dạng:

~~~java
public interface AutoCloseable {
    void close() throws Exception;
}
~~~

Chữ ký trên mô tả API ở mức cơ bản. Một lớp triển khai được phép **thu hẹp hoặc bỏ** ngoại lệ checked trong `close()`:

~~~java
static final class SimpleResource implements AutoCloseable {
    private final String name;

    SimpleResource(String name) {
        this.name = name;
        System.out.println("open " + name);
    }

    @Override
    public void close() {
        System.out.println("close " + name);
    }
}
~~~

Đây là khai báo lớp lồng có thể đặt trong một lớp Java. `SimpleResource.close()` không khai báo checked exception nên mã sử dụng nó không phải xử lý `Exception` chỉ vì định nghĩa chung của `AutoCloseable` có `throws Exception`.

Cú pháp một tài nguyên:

~~~java
try (SimpleResource r = new SimpleResource("A")) {
    System.out.println("body");
}
~~~

Dự đoán stdout:

~~~text
open A
body
close A
~~~

Khi có nhiều tài nguyên, viết các khai báo trong cặp ngoặc sau `try`, ngăn cách bằng dấu chấm phẩy:

~~~java
try (SimpleResource a = new SimpleResource("A");
     SimpleResource b = new SimpleResource("B")) {
    System.out.println("body");
}
~~~

Kết quả:

~~~text
open A
open B
body
close B
close A
~~~

**Điểm phân biệt:** `AutoCloseable.close()` có thể ném `Exception`, còn `java.io.Closeable.close()` khai báo `IOException` và thường dùng cho các API I/O. Các lớp cụ thể có thể có chữ ký hẹp hơn. Tác động tới `throws` của phương thức phụ thuộc kiểu tĩnh của tài nguyên và các checked exception có thể thoát khỏi `close()`.

## 3. Java đóng lúc nào?

Việc đóng tài nguyên xảy ra khi phần thân try-with-resources **hoàn tất theo bất kỳ cách hợp lệ nào khiến cấu trúc cần được rời**:

- Phần thân chạy hết câu lệnh bình thường.
- Phần thân chuẩn bị `return` một giá trị.
- Phần thân ném ngoại lệ, dù sau đó có `catch` xử lý.
- `break` hoặc `continue` khiến luồng điều khiển rời khỏi phạm vi try-with-resources tương ứng.

Nếu thân `try` đang chờ vô hạn hoặc vòng lặp không có đường thoát, không có cơ chế tự động “hẹn giờ đóng”. Tương tự, tiến trình bị kết thúc cưỡng bức không có bảo đảm sẽ chạy `close()`. Những điều này không làm thay đổi thứ tự đóng **nếu** Java có cơ hội thực hiện việc đóng.

### `return` vẫn đóng trước khi caller nhận giá trị

~~~java
static int returnAfterClosing() {
    try (SimpleResource a = new SimpleResource("A");
         SimpleResource b = new SimpleResource("B")) {
        System.out.println("prepare return");
        return 7;
    }
}
~~~

Nếu caller chạy `System.out.println("value=" + returnAfterClosing());`:

~~~text
open A
open B
prepare return
close B
close A
value=7
~~~

`return` định ra giá trị trước, còn cả hai tài nguyên được đóng trước khi phương thức thực sự hoàn tất và caller nhận `7`. Nếu một `close()` phát sinh ngoại lệ, quá trình trả kết quả có thể bị thay thế bởi việc ném ngoại lệ — sẽ giải thích ở phần lỗi khi đóng.

## 4. Một chương trình Java 17+ đầy đủ để quan sát thứ tự

Chương trình dưới đây chạy nhiều trường hợp với những tài nguyên tự định nghĩa để đầu ra rõ ràng. Mỗi tài nguyên in một dòng khi mở và một dòng khi đóng; một số tài nguyên được cấu hình để **ném `IOException` khi đóng**.

Tạo tệp **`ResourceCloseOrderDemo.java`**:

~~~java
import java.io.IOException;

public class ResourceCloseOrderDemo {

    static final class Tracked implements AutoCloseable {
        private final String name;
        private final boolean failOnClose;

        Tracked(String name, boolean failOnClose) {
            this.name = name;
            this.failOnClose = failOnClose;
            System.out.println("open " + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            if (failOnClose) {
                throw new IOException("close-" + name);
            }
        }
    }

    public static void main(String[] args) {
        System.out.println("== normal ==");
        normal();

        System.out.println("== body failure ==");
        bodyFailure();

        System.out.println("== close failure ==");
        closeFailure();

        System.out.println("== initialization failure ==");
        initializationFailure();

        System.out.println("== return ==");
        System.out.println("result=" + returnEarly());
    }

    static void normal() {
        try (Tracked a = new Tracked("A", false);
             Tracked b = new Tracked("B", false);
             Tracked c = new Tracked("C", false)) {
            System.out.println("body ok");
        } catch (IOException e) {
            System.out.println("unexpected: " + e.getMessage());
        }
    }

    static void bodyFailure() {
        try (Tracked a = new Tracked("A", true);
             Tracked b = new Tracked("B", true)) {
            System.out.println("body throws");
            throw new IllegalArgumentException("work");
        } catch (IllegalArgumentException e) {
            System.out.println("primary=" + e.getMessage());
            printSuppressed(e);
        } catch (IOException e) {
            System.out.println("unexpected I/O: " + e.getMessage());
        }
    }

    static void closeFailure() {
        try (Tracked a = new Tracked("A", true);
             Tracked b = new Tracked("B", true)) {
            System.out.println("body ok");
        } catch (IOException e) {
            System.out.println("primary=" + e.getMessage());
            printSuppressed(e);
        }
    }

    static void initializationFailure() {
        try (Tracked a = new Tracked("A", true);
             Tracked b = new Tracked("B", true);
             Tracked c = failToInitializeC()) {
            System.out.println("body not reached");
        } catch (IOException e) {
            System.out.println("primary=" + e.getMessage());
            printSuppressed(e);
        }
    }

    static Tracked failToInitializeC() throws IOException {
        System.out.println("open C failed");
        throw new IOException("init-C");
    }

    static int returnEarly() throws IOException {
        try (Tracked a = new Tracked("A", false);
             Tracked b = new Tracked("B", false)) {
            System.out.println("return prepared");
            return 7;
        }
    }

    static void printSuppressed(Throwable e) {
        for (Throwable s : e.getSuppressed()) {
            System.out.println("suppressed=" + s.getMessage());
        }
    }
}
~~~

Biên dịch và chạy (Java 17 trở lên):

~~~bash
javac ResourceCloseOrderDemo.java
java ResourceCloseOrderDemo
~~~

**Stdout chính xác:**

~~~text
== normal ==
open A
open B
open C
body ok
close C
close B
close A
== body failure ==
open A
open B
body throws
close B
close A
primary=work
suppressed=close-B
suppressed=close-A
== close failure ==
open A
open B
body ok
close B
close A
primary=close-B
suppressed=close-A
== initialization failure ==
open A
open B
open C failed
close B
close A
primary=init-C
suppressed=close-B
suppressed=close-A
== return ==
open A
open B
return prepared
close B
close A
result=7
~~~

### Kiểm chứng trường hợp bình thường

Phần `normal()` khởi tạo ba đối tượng `A`, `B`, `C`. Sau `body ok`, Java lần lượt gọi `C.close()`, `B.close()` và `A.close()`. Không có ngoại lệ nên nhánh `catch` không chạy.

### Kiểm chứng trường hợp thân `try` ném ngoại lệ

Phần `bodyFailure()` có ngoại lệ chính `IllegalArgumentException("work")`. Dù thân `try` đã ném lỗi, Java vẫn thử đóng `B` rồi `A`. Hai lệnh `close()` cũng ném `IOException`, nhưng **chúng không thay thế ngoại lệ `work` đang là lỗi chính**: lỗi đóng được thêm vào danh sách **suppressed exceptions** của ngoại lệ chính.

Do `B` đóng trước, `close-B` xuất hiện trước `close-A` trong `getSuppressed()`. Tên loại ngoại lệ chính vẫn là `IllegalArgumentException` và thông điệp chính vẫn là `work`.

### Kiểm chứng trường hợp chỉ `close()` bị lỗi

Phần `closeFailure()` có thân `try` hoàn tất bình thường. Khi đóng `B`, `IOException("close-B")` được ném; Java tiếp tục đóng `A`. Lỗi `close-A` phát sinh sau, nên được lưu là *suppressed* của ngoại lệ `close-B`. Sau khi quá trình đóng kết thúc, `catch (IOException e)` nhận lỗi chính `close-B`.

Cần phân biệt: ở tình huống **thân `try` không lỗi**, lỗi đóng tài nguyên đầu tiên theo thứ tự đóng có thể trở thành ngoại lệ chính.

### Kiểm chứng trường hợp khởi tạo chưa hết tài nguyên

Phần `initializationFailure()` tạo `A` rồi `B` thành công. Đến tài nguyên `C`, biểu thức khởi tạo `failToInitializeC()` ném `IOException("init-C")` **trước khi tạo thành công đối tượng `C`**. Java không chạy thân `try`, cũng không có tài nguyên `C` đã khởi tạo thành công để tự động đóng.

Tuy nhiên, `B` và `A` đã được tạo thành công trước đó nên vẫn được đóng **theo chiều ngược**, tức `B` trước `A`. Nếu việc đóng gây lỗi, chúng được ghi nhận là suppressed exceptions của lỗi khởi tạo `init-C`.

### Kiểm chứng trường hợp `return`

Phần `returnEarly()` chuẩn bị trả `7` nhưng vẫn phải đóng `B` rồi `A` trước khi caller in `result=7`. Chữ ký `throws IOException` của phương thức hợp lý vì `Tracked.close()` có thể ném `IOException`, dù trong lần chạy này cả hai tài nguyên đều không được cấu hình gây lỗi khi đóng.

## 5. Nếu tài nguyên thứ hai hoặc thứ ba khởi tạo thất bại

Hãy phân biệt hai tình huống:

**Tình huống A — Khởi tạo `B` thất bại:**

~~~java
try (Resource a = openA();
     Resource b = openBThatThrows();
     Resource c = openC()) {
    runTask();
}
~~~

Đây là mã giả dùng để giải thích thứ tự. Khi `openA()` hoàn tất và `openBThatThrows()` ném lỗi:

1. `A` đã được khởi tạo thành công.
2. `B` chưa được xác lập là tài nguyên đã tạo thành công; `C` chưa được khởi tạo.
3. Thân `try` không được thực thi.
4. Java đóng `A`.
5. Ngoại lệ từ việc khởi tạo `B` tiếp tục lan ra ngoài; lỗi khi đóng `A` có thể được suppressed vào ngoại lệ đó.

**Tình huống B — Khởi tạo `C` thất bại:** `A` và `B` đã được khởi tạo, nên cả hai được đóng theo thứ tự `B` rồi `A` như ví dụ Java chạy được ở phần 4.

Không nói “bất cứ tài nguyên nào được nhắc đến trong header đều được đóng”: chỉ những tài nguyên **đã được khởi tạo thành công và được quản lý bởi cấu trúc** mới có `close()` tự động. Với một constructor bị lỗi giữa chừng, phần tài nguyên nội bộ mà constructor đã mở nhưng chưa bàn giao có thể cần được chính constructor hoặc hàm tạo **tự dọn dẹp**; try-with-resources bên ngoài không thể tự động đóng một đối tượng chưa được khởi tạo thành công.

## 6. Cơ chế ngoại lệ chính và suppressed exceptions

Sử dụng nhiều tài nguyên thường đặt ra tình huống: **thân `try` thất bại, rồi một hoặc nhiều tài nguyên lại thất bại khi đóng**. Java không muốn lỗi dọn dẹp vô tình che khuất nguyên nhân chính.

Giả sử:

~~~text
body:       throw WorkException("work")
close C:    throw IOException("close C")
close B:    return normally
close A:    throw IOException("close A")
~~~

Với try-with-resources, quan hệ lỗi được tổ chức như sau:

~~~text
Primary exception:
  WorkException("work")
  ├── suppressed: IOException("close C")
  └── suppressed: IOException("close A")
~~~

Thứ tự suppressed phản ánh **thứ tự thực tế lỗi được thêm khi các tài nguyên đóng**, thường tương ứng với thứ tự đóng ngược: `C` rồi `A` trong ví dụ.

### Trường hợp thân `try` thành công nhưng nhiều `close()` lỗi

Giả sử `A` và `B` được mở, thân `try` kết thúc bình thường, `B.close()` ném lỗi, rồi `A.close()` cũng ném lỗi:

~~~text
Primary:    IOException("close B")
Suppressed: IOException("close A")
~~~

Không có ngoại lệ từ thân `try` để làm primary, nên ngoại lệ đóng đầu tiên được giữ làm primary. Các lỗi đóng tiếp theo được đính kèm vào nó.

### Cách đọc trong code

~~~java
try (Tracked a = new Tracked("A", true);
     Tracked b = new Tracked("B", true)) {
    throw new IllegalStateException("operation failed");
} catch (Exception e) {
    System.out.println("Primary: " + e.getMessage());
    for (Throwable suppressed : e.getSuppressed()) {
        System.out.println("Suppressed: " + suppressed.getMessage());
    }
}
~~~

Đây là **đoạn minh họa** dùng lớp `Tracked` trong chương trình chính. Nó in lỗi chính từ thân `try` và các lỗi đóng được giữ lại. `getSuppressed()` trả về mảng chứa các ngoại lệ đã được đính kèm, không tự biến chúng thành `getCause()`.

Phân biệt:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `getCause()` | Một ngoại lệ/nguyên nhân được liên kết bằng cause |
| `getSuppressed()` | Các ngoại lệ phụ bị giữ lại khi ngoại lệ chính vẫn được ưu tiên |
| `getMessage()` | Thông điệp của chính đối tượng ngoại lệ đang xem |
| `printStackTrace()` | Có thể hiển thị lỗi chính, cause và suppressed để chẩn đoán |

**Suppressed exceptions không đồng nghĩa mọi lỗi đều được bỏ qua.** Chúng vẫn quan trọng để điều tra tài nguyên nào thất bại khi đóng. Không nên chỉ log `e.getMessage()` nếu cần giữ đầy đủ thông tin đóng tài nguyên.

## 7. Try-with-resources khác `finally { close(); }` viết thủ công ra sao?

Mẫu đóng bằng tay:

~~~java
Resource a = openA();
Resource b = openB();
try {
    use(a, b);
} finally {
    b.close();
    a.close();
}
~~~

Đây là **mã giả minh họa**, không phải chương trình độc lập. Nó có ít nhất hai rủi ro:

1. Nếu `openB()` lỗi **trước khi vào `try`**, đoạn `finally` chưa bắt đầu quản lý `A`, dẫn tới bỏ sót đóng tài nguyên đã mở.
2. Nếu `b.close()` ném lỗi, câu lệnh `a.close()` ở sau **có thể không được thực thi**, vì luồng chuyển ra khỏi `finally` trước khi tới dòng đó.

Với try-with-resources, Java sắp đặt cơ chế đóng để các tài nguyên đã khởi tạo thành công được **thử đóng theo chiều ngược**, kể cả khi việc đóng tài nguyên ở phía sau ném lỗi. Ngoài ra, Java còn quản lý suppressed exceptions theo quy tắc, tránh vô tình làm mất lỗi từ thân `try`.

Một phiên bản `finally` thủ công chắc chắn hơn cần các `try/finally` lồng nhau, xử lý ngoại lệ riêng cho từng lần đóng và quản lý quá trình khởi tạo dở dang — dễ sai và khó đọc hơn. Đây là lý do **ưu tiên try-with-resources** khi tài nguyên triển khai `AutoCloseable`.

### Sơ đồ ý tưởng của việc đóng ngược

~~~text
Tạo A thành công
  └── Tạo B thành công
        └── Tạo C thành công
              └── Chạy body
                  └── Đóng C
              └── Đóng B
          └── Đóng A
~~~

Đây là **sơ đồ khái niệm**, không phải phép biến đổi chính xác từng bytecode. Java có thể dùng logic tương đương các khối `try/finally` lồng nhau, đồng thời theo dõi primary exception và các lỗi bị suppressed.

## 8. Thứ tự đóng và vòng đời của tài nguyên phụ thuộc

Các tài nguyên có thể không độc lập. Ví dụ API thường có tầng đọc dữ liệu:

~~~java
try (java.io.InputStream raw =
             java.nio.file.Files.newInputStream(path);
     java.io.InputStreamReader decoder =
             new java.io.InputStreamReader(raw,
                     java.nio.charset.StandardCharsets.UTF_8);
     java.io.BufferedReader buffered =
             new java.io.BufferedReader(decoder)) {
    System.out.println(buffered.readLine());
}
~~~

Đây là đoạn minh họa cần biến `path` kiểu `Path` và xử lý `IOException` thích hợp ở phương thức bao quanh.

Trình tự quản lý của chính cấu trúc trên là:

1. Khởi tạo `raw`.
2. Khởi tạo `decoder` từ `raw`.
3. Khởi tạo `buffered` từ `decoder`.
4. Đọc dữ liệu.
5. Gọi `buffered.close()`, rồi `decoder.close()`, rồi `raw.close()`.

**Cảnh báo về đóng lặp:** Các lớp wrapper của Java thường **tự đóng tài nguyên bên dưới** khi `close()`. Vì vậy ví dụ đưa cả ba tài nguyên vào cùng header là cách minh họa thứ tự, nhưng trong thiết kế thực tế nó có thể khiến tầng bên dưới nhận nhiều lần đóng. Không nên mặc định mọi loại tài nguyên chịu được `close()` lặp hoặc mọi wrapper có cùng chính sách ownership.

Với một chuỗi wrapper mà wrapper ngoài có quyền sở hữu tài nguyên bên trong, có thể cân nhắc để **chỉ wrapper ngoài quản lý việc đóng**, theo hợp đồng API cụ thể:

~~~java
try (java.io.BufferedReader reader =
             java.nio.file.Files.newBufferedReader(
                     path, java.nio.charset.StandardCharsets.UTF_8)) {
    System.out.println(reader.readLine());
}
~~~

Đây là một đoạn minh họa dùng phương thức `Files.newBufferedReader`. Caller không phải tự liệt kê cả các tầng stream/decoder khi API trả về một tài nguyên đóng đúng trách nhiệm của nó.

Nguyên tắc **ownership** quan trọng không kém thứ tự: thành phần nào được giao trách nhiệm đóng, tài nguyên có được chia sẻ hay không, và việc đóng wrapper có kéo theo đóng tài nguyên gốc không.

## 9. Tài nguyên có sẵn từ trước và cú pháp Java 9+

Từ Java 9, có thể đưa vào try-with-resources một **biến tài nguyên đã tồn tại**, nếu nó là `final` hoặc **effectively final** và thỏa kiểu `AutoCloseable`:

~~~java
Tracked resource = new Tracked("existing", false);

try (resource) {
    System.out.println("use existing");
}
~~~

Đây là đoạn minh họa dùng lớp `Tracked` trong chương trình trước. Khi vùng `try` kết thúc, tài nguyên được đóng tự động dù nó đã được khởi tạo trước phần đầu `try`.

Với nhiều biến đã có, thứ tự xuất hiện trong danh sách vẫn quyết định thứ tự đóng:

~~~java
Tracked first = new Tracked("first", false);
Tracked second = new Tracked("second", false);

try (first; second) {
    System.out.println("body");
}
~~~

Đóng `second` trước `first`.

**Lưu ý:** Trong ví dụ biến đã có, thứ tự tạo thật sự xảy ra ở các câu lệnh trước `try`; quy tắc đóng dựa vào **thứ tự liệt kê trong phần đầu try-with-resources**, không phải khả năng “nhớ lịch sử tạo đối tượng” của JVM. Chẳng hạn có thể khai báo `try (second; first)` và sẽ đóng `first` trước `second`. Do đó cách phát biểu “ngược thứ tự tạo” chuẩn nhất khi nói về **các khai báo tạo tài nguyên ngay trong phần đầu `try`**. Khi dùng biến đã tạo từ trước, cần nói chính xác là **ngược thứ tự tài nguyên trong danh sách quản lý**.

Không nên dùng lại cùng đối tượng tài nguyên trong nhiều mục của danh sách như một mẹo: nó có thể dẫn đến gọi `close()` nhiều lần trên cùng đối tượng, vi phạm giả định ownership của một số API.

## 10. Trường hợp tài nguyên là `null`

Một biến tài nguyên có thể được khởi tạo bằng `null` nếu kiểu hợp lệ:

~~~java
AutoCloseable optional = null;
try (optional) {
    System.out.println("body");
}
~~~

Đây là ví dụ hợp lệ từ Java 9 trở lên vì `optional` là effectively final. Khi kết thúc khối, Java **không gọi `close()` lên một tham chiếu `null`**. Nó không phát sinh `NullPointerException` chỉ vì mục tài nguyên trong phần đầu `try` là `null`.

Tuy nhiên, điều đó không có nghĩa mọi tài nguyên nên cho phép `null` trong thiết kế API. Nếu thiếu tài nguyên là trạng thái không hợp lệ, nên kiểm tra và báo lỗi rõ ràng thay vì dùng `null` để bỏ qua công việc cần thiết.

Nếu các mục `A`, `B`, `C` gồm `B == null` thì phần đóng hiệu lực là `C` rồi `A`; mục `B` không có đối tượng để đóng.

## 11. Thứ tự đóng với `catch` và `finally` của cùng cấu trúc

Try-with-resources có thể đi cùng các nhánh `catch` và `finally`:

~~~java
try (Tracked a = new Tracked("A", false);
     Tracked b = new Tracked("B", false)) {
    System.out.println("body");
} catch (java.io.IOException e) {
    System.out.println("catch: " + e.getMessage());
} finally {
    System.out.println("finally");
}
~~~

Đoạn này dùng lớp `Tracked` đã định nghĩa trước. Nếu không có lỗi, thứ tự in:

~~~text
open A
open B
body
close B
close A
finally
~~~

**Tài nguyên được đóng trước khi chạy nhánh `catch` hoặc `finally` đi kèm cấu trúc try-with-resources.** Nếu lỗi từ thân `try` hoặc lỗi khi đóng xảy ra, các nhánh `catch` sẽ nhìn thấy ngoại lệ sau khi quá trình đóng đã được thực hiện theo quy tắc. `finally` chạy sau nhánh `catch` tương ứng.

Ví dụ nếu `B.close()` ném `IOException` mà thân `try` không ném lỗi, `catch (IOException e)` sẽ nhận lỗi khi đóng. Nếu thân `try` ném `IllegalArgumentException` và `B.close()` ném `IOException`, `catch (IOException e)` **không** tự động nhận lỗi suppressed đó như ngoại lệ chính; cần có handler phù hợp với ngoại lệ đang truyền và kiểm tra `getSuppressed()` nếu cần.

## 12. Khi `close()` ném lỗi, Java còn đóng tài nguyên trước đó không?

**Có — theo quy tắc try-with-resources**, Java cố gắng đóng những tài nguyên đã được khởi tạo thành công còn lại theo thứ tự ngược, ngay cả khi một lệnh `close()` vừa ném ngoại lệ.

Điều này tạo ra điểm khác với đoạn `finally` thủ công chỉ liệt kê:

~~~java
finally {
    b.close();
    a.close();
}
~~~

Ở đoạn thủ công đó, nếu `b.close()` ném lỗi và không có thêm xử lý, Java không đi tiếp tới `a.close()`. Với try-with-resources, công việc đóng các tài nguyên còn lại được sắp đặt riêng và lỗi phát sinh được quản lý bằng suppressed exceptions.

Tuy vậy, cần hiểu giới hạn của chữ “cố gắng”:

- Nếu một `close()` **treo vô hạn**, luồng không thể đi tiếp để đóng tài nguyên còn lại.
- Nếu tiến trình bị kết thúc cưỡng bức, không thể bảo đảm các `close()` còn lại chạy.
- Nếu một `close()` thực hiện `System.exit` hoặc `Runtime.halt`, quy tắc chấm dứt JVM có thể ngăn đóng tiếp.
- Nếu code hoặc VM gặp lỗi quá nghiêm trọng để tiếp tục thực thi, không thể hứa dọn dẹp hoàn tất.

Try-with-resources cải thiện **thứ tự và quản lý lỗi trong luồng điều khiển Java bình thường**; nó không phải cơ chế bảo đảm an toàn bất chấp việc tiến trình không còn chạy.

## 13. AutoCloseable, Closeable và cách tự thiết kế tài nguyên

Khi tự viết một lớp `AutoCloseable`, nên xác định rõ:

- Một lần `close()` phải làm gì (đóng kết nối, giải phóng khóa, xả bộ đệm, hoàn tất giao dịch hay chỉ thu hồi tài nguyên).
- Có an toàn nếu gọi `close()` lặp không?
- `close()` có thể ném loại ngoại lệ nào?
- Tài nguyên có thể được nhiều thành phần cùng sở hữu không?
- Việc đóng một wrapper có tự đóng đối tượng bên dưới không?

Ví dụ lớp đơn giản được đóng an toàn khi gọi lại:

~~~java
static final class IdempotentResource implements AutoCloseable {
    private boolean closed;

    @Override
    public void close() {
        if (closed) {
            return;
        }
        closed = true;
        System.out.println("closed once");
    }
}
~~~

Đây là lớp lồng minh họa. Trong chương trình đa luồng, nếu một đối tượng có thể bị đóng đồng thời từ nhiều thread, cần thiết kế đồng bộ thích hợp; biến `closed` đơn thuần không đủ bảo đảm thread safety.

**Không phải `close()` của mọi thư viện đều idempotent.** Hãy xem hợp đồng của tài nguyên cụ thể, đặc biệt khi kết hợp những wrapper tự đóng tầng dưới và danh sách nhiều tài nguyên.

Nếu một tài nguyên cần xử lý nhiều bước khi đóng, hãy bảo đảm phần xử lý lỗi không vô tình bỏ qua bước quan trọng hoặc che nguyên nhân gốc. Trong các trường hợp phức tạp, cấu trúc thêm suppressed exceptions cho phép giữ thông tin của nhiều lỗi, nhưng vẫn cần chính sách ghi log và phản hồi thất bại phù hợp.

## 14. Những lỗi hiểu sai phổ biến

**Sai lầm 1: “Khai báo A rồi B thì Java đóng A trước.”**  
Không. Nếu chúng ở cùng phần đầu try-with-resources, Java đóng `B` trước `A`.

**Sai lầm 2: “Java đóng đồng thời các tài nguyên.”**  
Không. Các lời gọi `close()` được thực hiện có thứ tự theo quy tắc đóng ngược. Chỉ khi bản thân `close()` chủ động dùng bất đồng bộ thì hành vi nội bộ của nó có thể khác.

**Sai lầm 3: “Nếu body ném lỗi thì không đóng tài nguyên.”**  
Không. Những tài nguyên đã khởi tạo thành công vẫn được cố gắng đóng khi rời phạm vi `try`.

**Sai lầm 4: “Nếu đóng B bị lỗi thì A chắc chắn không được đóng.”**  
Không đúng với try-with-resources trong luồng Java bình thường. Java tiếp tục cố gắng đóng `A` và quản lý ngoại lệ bị suppressed.

**Sai lầm 5: “Nếu constructor của C lỗi, Java vẫn phải gọi `C.close()`.”**  
Không. Nếu `C` chưa được khởi tạo thành công thì nó không trở thành một tài nguyên đã được quản lý; `A` và `B` thành công trước đó mới được đóng theo quy tắc.

**Sai lầm 6: “Bất kỳ lỗi close nào cũng thay thế lỗi body.”**  
Không. Khi thân `try` đã ném lỗi chính, các lỗi close thường được đính kèm qua `getSuppressed()`.

**Sai lầm 7: “Nếu body không lỗi thì lỗi close chỉ là suppressed.”**  
Không. Lỗi đóng đầu tiên có thể là ngoại lệ chính khi không có lỗi khác đang truyền.

**Sai lầm 8: “`getCause()` và `getSuppressed()` giống nhau.”**  
Không. Cause mô tả một quan hệ nguyên nhân; suppressed giữ các lỗi bổ sung không thay thế primary exception.

**Sai lầm 9: “Đã viết `return` trong try thì caller nhận giá trị trước khi close.”**  
Không. Đóng xảy ra trước khi lời gọi hoàn tất. Nếu close ném checked exception, caller có thể nhận lỗi thay vì giá trị.

**Sai lầm 10: “Các biến tài nguyên tạo sẵn luôn đóng ngược thời gian chúng từng được tạo.”**  
Không. Với cú pháp Java 9+ `try (first; second)`, thứ tự đóng là ngược thứ tự **liệt kê trong header**, dù hai biến được tạo lúc nào.

**Sai lầm 11: “Wrapper ngoài và mọi tầng bên dưới đều phải khai báo trong cùng một header.”**  
Không nhất thiết. Đóng wrapper có thể tự đóng tầng dưới; cần hiểu hợp đồng ownership để tránh đóng trùng.

**Sai lầm 12: “Try-with-resources bảo đảm close sau khi JVM bị kill.”**  
Không. Khi không còn cơ hội chạy code Java, cả `finally` lẫn try-with-resources đều không thể bảo đảm được thực thi.

**Sai lầm 13: “Tài nguyên `null` sẽ làm close báo NullPointerException.”**  
Không. Một mục tài nguyên có giá trị `null` không bị gọi `close()` tự động.

**Sai lầm 14: “Có thể dùng bất kỳ đối tượng nào trong try (...) vì Java sẽ tìm phương thức close.”**  
Không. Kiểu tĩnh của tài nguyên phải tương thích với `AutoCloseable`; chỉ một phương thức trùng tên `close()` mà không triển khai giao diện phù hợp là chưa đủ.

## 15. Câu hỏi tự kiểm tra

1. Với `try (A a = ...; B b = ...; C c = ...)`, thứ tự khởi tạo và đóng lần lượt là gì?
2. Vì sao đóng tài nguyên theo LIFO thường hợp lý khi đối tượng mới được xây dựng từ đối tượng đã tồn tại?
3. Một phương thức `return` từ bên trong try-with-resources: tài nguyên đóng trước hay sau khi caller nhận kết quả?
4. Nếu thân `try` ném `IllegalArgumentException("work")`, `B.close()` và `A.close()` đều ném `IOException`, ngoại lệ nào là primary?
5. Trong câu 4, `getSuppressed()` chứa các lỗi theo thứ tự nào?
6. Nếu thân `try` chạy hết bình thường nhưng `B.close()` lỗi rồi `A.close()` lỗi, ngoại lệ nào là primary?
7. Nếu tài nguyên `C` khởi tạo thất bại, Java đóng những tài nguyên nào đã được khởi tạo thành công trước nó?
8. Nếu constructor của `B` mở một socket nội bộ rồi ném trước khi tạo thành công đối tượng `B`, ai phải chịu trách nhiệm thu hồi socket đó?
9. Vì sao `finally { b.close(); a.close(); }` viết thủ công có thể bỏ sót `a.close()`?
10. Trong try-with-resources có `catch` và `finally`, tài nguyên được đóng trước hay sau các khối đó?
11. Với `Tracked first` và `Tracked second` tạo sẵn, `try (second; first)` sẽ đóng theo thứ tự nào?
12. Nếu mục tài nguyên có giá trị `null`, Java có tự gọi `close()` lên `null` không?
13. Vì sao cùng đưa `BufferedReader` và `InputStream` bên dưới vào header đôi khi dẫn tới đóng trùng tài nguyên?
14. Có phải một lớp chỉ cần khai báo phương thức `void close()` là đủ được dùng trong try-with-resources không?
15. Try-with-resources có thể bảo đảm mọi tài nguyên được đóng khi một `close()` bị kẹt vô hạn không?
16. Khi thiết kế `AutoCloseable` riêng, tại sao cần xác định rõ ownership và hành vi nếu `close()` bị gọi nhiều lần?

### Đáp án gợi ý

1. Khởi tạo `A -> B -> C`, đóng `C -> B -> A`.
2. Để tầng mới dừng sử dụng tài nguyên bên dưới trước khi đóng tầng bên dưới.
3. Trước khi caller nhận kết quả.
4. Lỗi `work` từ thân `try` là primary.
5. `close-B` rồi `close-A` vì `B` đóng trước.
6. `close-B` là primary, `close-A` là suppressed.
7. Đóng `B` rồi `A`; không tự đóng `C` chưa khởi tạo thành công.
8. Constructor/hàm mở tài nguyên chịu trách nhiệm dọn dẹp phần chưa bàn giao.
9. Nếu `b.close()` ném lỗi, lệnh đóng `a` có thể không được thực hiện.
10. Trước các khối `catch` và `finally` gắn với cấu trúc đó.
11. Đóng `first` rồi `second`, ngược thứ tự liệt kê.
12. Không.
13. Wrapper thường đã đóng tài nguyên dưới khi `close()`, dẫn tới nhiều lần close.
14. Không, cần tương thích với `AutoCloseable`.
15. Không; luồng không thể tiến tới những lời gọi close còn lại nếu đang bị kẹt.
16. Để tránh đóng thiếu, đóng trùng hoặc làm hỏng tài nguyên được nhiều thành phần sử dụng.

## 16. Ghi nhớ

**Tài nguyên trong try-with-resources được khởi tạo từ trái sang phải và đóng từ phải sang trái**. Nếu thân `try` ném lỗi, Java vẫn cố gắng đóng các tài nguyên đã khởi tạo thành công; lỗi đóng thường được lưu dưới dạng **suppressed exceptions** của lỗi chính. Nếu không có lỗi trước đó, lỗi đóng đầu tiên có thể trở thành primary. Nếu quá trình khởi tạo dừng giữa chừng, những tài nguyên đã mở thành công vẫn được đóng ngược thứ tự. Với biến tài nguyên đã tạo từ trước trong Java 9+, thứ tự đóng dựa trên vị trí liệt kê trong header; hãy thiết kế ownership rõ ràng và dùng try-with-resources để tránh bỏ sót dọn dẹp so với `finally` thủ công.