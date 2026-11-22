# Xử lý khi việc tạo một tài nguyên thất bại trong Java `try-with-resources`

Trong Java, `try-with-resources` không chỉ tự động đóng tài nguyên khi **phần thân `try`** kết thúc. Nó còn bảo vệ trường hợp tinh tế hơn: **một biểu thức khởi tạo tài nguyên trong phần đầu `try (...)` bị lỗi trước khi phần thân bắt đầu chạy**. Khi ấy, Java phải dọn dẹp những tài nguyên đã khởi tạo thành công trước đó, giữ thông tin ngoại lệ chính và chuyển lỗi đến bộ xử lý thích hợp.

Ví dụ:

~~~java
try (Resource a = openA();
     Resource b = openB();
     Resource c = openC()) {
    use(a, b, c);
}
~~~

Nếu `openA()` thành công nhưng `openB()` ném ngoại lệ, Java **đóng `a`**, **không gọi `openC()`**, **không chạy `use(a,b,c)`**, rồi truyền ngoại lệ từ `openB()` ra ngoài. Java **không tự gọi `close()` trên một đối tượng `b` chưa được khởi tạo hoàn tất**. Nếu `a.close()` cũng thất bại, ngoại lệ đóng được gắn dưới dạng **suppressed exception** của lỗi khởi tạo B (với cơ chế suppression thông thường).

Bài này giải thích chính xác thứ tự khởi tạo, đóng, bắt ngoại lệ và `finally` trên Java 17+; phân biệt lỗi mở tài nguyên với lỗi sử dụng tài nguyên; chỉ ra giới hạn khi constructor cấp phát tài nguyên rồi thất bại; và đưa ra các ví dụ chạy được cùng hướng thiết kế an toàn.

## 1. Điều kiện để một tài nguyên được quản lý tự động

`try-with-resources` hỗ trợ những tài nguyên có kiểu thực thi `AutoCloseable`, trong đó phổ biến có `Closeable` như `InputStream`, `Reader` hay đối tượng kết nối tùy API. Phần `try (...)` khai báo một hoặc nhiều resource variable:

~~~java
try (java.io.InputStream in = java.nio.file.Files.newInputStream(path)) {
    int firstByte = in.read();
    System.out.println(firstByte);
}
~~~

Đây là **đoạn minh họa trong một phương thức** có biến `path` kiểu `Path` và xử lý hoặc khai báo `IOException`. Nếu biểu thức `Files.newInputStream(path)` thành công và trả về stream khác `null`, stream đó được Java quản lý và `close()` sẽ được gọi khi rời cấu trúc thích hợp, kể cả khi phần thân ném ngoại lệ.

Các đặc điểm cần nhớ:

1. **Khởi tạo từ trái sang phải.** Mỗi biểu thức mở tài nguyên phải hoàn thành bình thường thì Java mới bắt đầu biểu thức tiếp theo.
2. **Đóng theo thứ tự ngược.** Những tài nguyên đã khởi tạo thành công được đóng từ phải sang trái khi rời phạm vi.
3. **Phần thân chỉ chạy sau khi toàn bộ biểu thức tài nguyên cần thiết hoàn tất bình thường.**
4. **Một biểu thức khởi tạo thất bại** khiến phần thân không chạy; các tài nguyên đã khởi tạo trước đó vẫn cần được đóng.
5. `catch` và `finally` đi kèm của chính cấu trúc `try-with-resources` được thực hiện **sau bước dọn dẹp tự động** của các tài nguyên đã được quản lý.
6. Nếu biểu thức tài nguyên trả `null` **mà không ném lỗi**, biểu thức đó vẫn hoàn tất bình thường; Java bỏ qua việc `close()` cho tham chiếu `null`. Điều này khác với *khởi tạo ném ngoại lệ*.

Không được nhầm “đã bắt đầu chạy constructor” với “resource variable đã hoàn tất khởi tạo và được đưa vào phạm vi tự quản lý”. Nếu constructor ném trước khi trả về một đối tượng hợp lệ, biến tài nguyên tương ứng không được khởi tạo hoàn tất để Java tự gọi `close()` trên nó.

## 2. Luồng thực thi nếu một tài nguyên ở giữa danh sách thất bại

Giả sử có ba tài nguyên A, B và C, được khai báo theo thứ tự đó:

~~~java
try (Resource a = openA();
     Resource b = openB();
     Resource c = openC()) {
    System.out.println("Thân try");
} catch (IOException ex) {
    System.out.println("Lỗi: " + ex.getMessage());
} finally {
    System.out.println("Kết thúc cấu trúc");
}
~~~

Đây là **khung minh họa**, cần định nghĩa `Resource`, `openA/B/C()` và các import/chữ ký tương ứng. Nếu A thành công nhưng B ném `IOException`, luồng diễn ra như sau:

~~~text
Bước 1: Đánh giá openA()
        └── Thành công → A trở thành tài nguyên được quản lý

Bước 2: Đánh giá openB()
        └── Ném IOException → dừng khởi tạo danh sách

Bước 3: C không được khởi tạo; thân try không chạy

Bước 4: Đóng A bằng A.close()
        ├── Nếu thành công: giữ nguyên IOException từ B
        └── Nếu ném lỗi: bổ sung lỗi đóng vào suppressed của lỗi B

Bước 5: Chuyển đến catch (IOException), nếu phù hợp

Bước 6: Thực thi finally đi kèm

Bước 7: Tiếp tục hoặc truyền ngoại lệ, tùy cách catch/finally kết thúc
~~~

**Mấu chốt:** lỗi từ B không làm quên A; A được đóng dù phần thân `try` chưa hề thực thi. C thì không có lời gọi tạo nên không có đối tượng C phải đóng. Đừng dự đoán thứ tự từ tên biến hay kiểu ngoại lệ: phải xem **thứ tự khai báo và điểm lỗi thực tế**.

Nếu có nhiều tài nguyên đã hoàn tất khởi tạo, ví dụ A và B thành công còn C lỗi, Java đóng **B rồi A**. Nếu chính quá trình đóng ném ngoại lệ, các lỗi đóng được ghi nhận thành các suppressed exception, trong khi lỗi khởi tạo C vẫn là ngoại lệ chính của đường thoát đó.

## 3. Ví dụ Java 17+ hoàn chỉnh: tài nguyên B tạo thất bại, đóng A cũng lỗi

Tạo tệp `ResourceInitFailureDemo.java`:

~~~java
import java.io.IOException;

public class ResourceInitFailureDemo {
    static final class Resource implements AutoCloseable {
        private final String name;
        private final boolean failOnClose;

        Resource(String name, boolean failOnOpen, boolean failOnClose)
                throws IOException {
            System.out.println("Bắt đầu tạo " + name);
            if (failOnOpen) {
                throw new IOException("Tạo " + name + " thất bại");
            }
            this.name = name;
            this.failOnClose = failOnClose;
            System.out.println("Đã tạo " + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("Đóng " + name);
            if (failOnClose) {
                throw new IOException("Đóng " + name + " thất bại");
            }
        }
    }

    public static void main(String[] args) {
        try (Resource a = new Resource("A", false, true);
             Resource b = new Resource("B", true, false);
             Resource c = new Resource("C", false, false)) {
            System.out.println("Trong thân try");
        } catch (IOException ex) {
            System.out.println("Lỗi chính: " + ex.getMessage());
            System.out.println("Số lỗi suppressed: " + ex.getSuppressed().length);
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("Suppressed: " + suppressed.getMessage());
            }
        } finally {
            System.out.println("Cuối cấu trúc");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ResourceInitFailureDemo.java
java ResourceInitFailureDemo
~~~

Stdout **chính xác**:

~~~text
Bắt đầu tạo A
Đã tạo A
Bắt đầu tạo B
Đóng A
Lỗi chính: Tạo B thất bại
Số lỗi suppressed: 1
Suppressed: Đóng A thất bại
Cuối cấu trúc
~~~

### Diễn giải từng dòng

- `new Resource("A", false, true)` ghi hai dòng đầu: A khởi tạo thành công, được đưa vào danh sách quản lý. Tham số cuối `true` mô phỏng việc `A.close()` sẽ ném `IOException`.
- `new Resource("B", true, false)` in `Bắt đầu tạo B`, sau đó ném `IOException("Tạo B thất bại")` **trong constructor**, trước khi hoàn tất gán các field và trước khi tạo xong resource B.
- Ngay khi biểu thức B thất bại, Java dừng xử lý danh sách: không thấy `Bắt đầu tạo C` và không thấy `Trong thân try`.
- Java gọi `A.close()`, in `Đóng A`. Vì `close()` của A cũng ném, lỗi đóng A được gắn làm **suppressed** của lỗi chính.
- `catch (IOException ex)` nhận lỗi `Tạo B thất bại`, chứ không phải lỗi `Đóng A thất bại`, vì cơ chế `try-with-resources` giữ ưu tiên cho lỗi khởi tạo đã xảy ra trước khi bắt đầu cleanup.
- `ex.getSuppressed()` trả mảng chứa một lỗi từ `A.close()`. `finally` chạy sau `catch`.

Trong ví dụ, `catch` kết thúc bình thường nên chương trình không ném lỗi ra khỏi `main`. Nếu không có `catch` phù hợp, lỗi từ B được truyền lên người gọi **sau khi** quá trình đóng A hoàn tất. `finally` đi kèm vẫn chạy trên đường lan truyền, nếu môi trường thực thi tiếp tục bình thường.

Đây là trường hợp thực tế cần quan sát cả **lỗi chính** và **suppressed**, vì nếu chỉ ghi `ex.getMessage()` thì bạn nhìn thấy nguyên nhân mở B thất bại nhưng bỏ qua thông tin A cũng không được đóng thành công.

## 4. Nếu tài nguyên đầu tiên tạo thất bại thì sao?

Khi ngay **biểu thức tài nguyên đầu tiên** ném lỗi, chưa có tài nguyên nào trong danh sách khởi tạo thành công để `try-with-resources` gọi `close()`. Phần thân `try` không chạy. `catch` bên ngoài phần quản lý tự động vẫn có thể bắt lỗi, và `finally` vẫn thực thi theo quy tắc của cấu trúc.

Tệp `FirstInitFailureDemo.java` minh họa:

~~~java
import java.io.IOException;

public class FirstInitFailureDemo {
    static final class Resource implements AutoCloseable {
        Resource() throws IOException {
            System.out.println("Tạo tài nguyên đầu tiên");
            throw new IOException("Không khởi tạo được");
        }

        @Override
        public void close() {
            System.out.println("Không bao giờ in: close()");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("Không bao giờ in: thân try");
        } catch (IOException ex) {
            System.out.println("Bắt lỗi: " + ex.getMessage());
        } finally {
            System.out.println("Finally chạy");
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 FirstInitFailureDemo.java
java FirstInitFailureDemo
~~~

Stdout chính xác:

~~~text
Tạo tài nguyên đầu tiên
Bắt lỗi: Không khởi tạo được
Finally chạy
~~~

Không có dòng `close()` vì constructor **không tạo xong** resource đầu tiên, và không có dòng trong thân `try`. Đừng nhầm điều này với bảo đảm rằng constructor không để rò rỉ thứ gì: nếu constructor đã mở một file hoặc giữ một tài nguyên con trước khi ném, đối tượng bao ngoài chưa hoàn tất khởi tạo **không được đóng tự động** theo `try-with-resources` ở nơi gọi. Đó là trách nhiệm của chính code khởi tạo hoặc factory, được bàn ở phần 8.

## 5. Nếu tất cả khởi tạo xong rồi phần thân `try` ném lỗi

Cần phân biệt **lỗi ở resource initializer** với **lỗi ở phần thân**. Khi tất cả tài nguyên đã tạo thành công, phần thân mới chạy. Nếu body ném ngoại lệ, Java cũng đóng các tài nguyên ngược thứ tự; nếu một `close()` ném lỗi thì ngoại lệ đóng có thể là suppressed của lỗi từ body.

Tệp `CompletedInitDemo.java`:

~~~java
import java.io.IOException;

public class CompletedInitDemo {
    static final class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("Tạo " + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("Đóng " + name);
            if (name.equals("B")) {
                throw new IOException("Lỗi đóng B");
            }
        }
    }

    public static void main(String[] args) {
        try (Resource a = new Resource("A");
             Resource b = new Resource("B")) {
            System.out.println("Trong thân try");
            throw new IllegalStateException("Lỗi xử lý");
        } catch (Exception ex) {
            System.out.println("Lỗi chính: " + ex.getMessage());
            System.out.println("Suppressed: " + ex.getSuppressed()[0].getMessage());
        }
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 CompletedInitDemo.java
java CompletedInitDemo
~~~

Stdout:

~~~text
Tạo A
Tạo B
Trong thân try
Đóng B
Đóng A
Lỗi chính: Lỗi xử lý
Suppressed: Lỗi đóng B
~~~

Ở đây, khác với mục 3, cả A và B đã được tạo xong nên **cả hai đều được đóng**, theo thứ tự B rồi A. Lỗi từ thân `try` là `IllegalStateException`; lỗi khi đóng B được lưu như suppressed. Java không bỏ qua việc đóng A chỉ vì đóng B đã thất bại.

Đừng suy ra `try-with-resources` làm mọi lỗi đóng biến mất. Nó **ghi nhận** chúng; bạn cần xem stack trace hoặc `getSuppressed()` để biết một số tài nguyên có thể đã thất bại trong lúc đóng. Ngoại lệ chính có thể đến từ **khởi tạo**, **body** hoặc **đóng**, tùy đường thực thi.

## 6. Trường hợp nhiều tài nguyên: ma trận các đường thất bại

Với:

~~~java
try (A a = openA();
     B b = openB();
     C c = openC()) {
    doWork(a, b, c);
}
~~~

Bảng sau giả định các tài nguyên được khởi tạo thành công trả về tham chiếu khác `null` và `close()` có thể được gọi theo hợp đồng `AutoCloseable`.

| Điểm xảy ra lỗi | Tài nguyên đã khởi tạo thành công | Những `close()` Java gọi | Body chạy? |
| --- | --- | --- | --- |
| `openA()` ném | Không có | Không có | Không |
| `openB()` ném | A | A | Không |
| `openC()` ném | A, B | B rồi A | Không |
| `doWork()` ném | A, B, C | C rồi B rồi A | Có, chạy đến điểm ném |
| Body hoàn tất bình thường | A, B, C | C rồi B rồi A | Có |
| `C.close()` ném sau body bình thường | A, B, C | C rồi B rồi A | Có |

Nếu các `close()` trong một hàng cũng ném, Java vẫn cố đóng những tài nguyên còn lại. Với lỗi khởi tạo hoặc lỗi body làm ngoại lệ chính, những lỗi đóng được thêm vào **suppressed exceptions**. Nếu body thành công mà chính việc đóng tài nguyên ném, ngoại lệ đóng đầu tiên theo thứ tự đóng có thể trở thành lỗi chính, còn các lỗi đóng sau được suppressed.

Đối với tài nguyên trả về `null` mà initializer hoàn thành bình thường, Java **không gọi `close()` với `null`**; biểu thức tiếp theo vẫn được đánh giá và body vẫn có thể chạy. Nếu API không cho phép kết quả `null`, nên kiểm tra điều kiện ấy trong factory, thay vì coi `null` là lỗi khởi tạo được runtime tự động ném.

## 7. Lỗi chính, `cause` và suppressed exceptions

Hai quan hệ thường xuất hiện khi xử lý ngoại lệ Java:

- **`getCause()`:** nguyên nhân được liên kết với một ngoại lệ qua constructor hoặc `initCause()`; hữu ích khi một lớp API bọc lỗi của tầng bên dưới.
- **`getSuppressed()`:** các ngoại lệ phụ được thêm qua `addSuppressed()` hoặc cơ chế tự động như `try-with-resources`; hữu ích khi một đường lỗi chính đồng thời có lỗi trong cleanup.

Trong ví dụ khởi tạo B thất bại rồi đóng A lỗi:

~~~text
IOException: Tạo B thất bại          <- lỗi chính
└── Suppressed: IOException: Đóng A thất bại
~~~

Đây là **suppressed**, không phải tự động thành `Caused by`. Nếu B được tạo bởi một factory chủ động bọc lỗi gốc bằng constructor `IOException(message, cause)`, bản thân lỗi khởi tạo B có thể còn có cause. Cả hai mối quan hệ có thể cùng tồn tại.

Đọc đầy đủ thông tin:

~~~java
// Đoạn minh họa bên trong catch (IOException ex).
System.out.println("Primary: " + ex);
Throwable cause = ex.getCause();
if (cause != null) {
    System.out.println("Cause: " + cause);
}
for (Throwable suppressed : ex.getSuppressed()) {
    System.out.println("Suppressed: " + suppressed);
}
~~~

Với logger chuẩn, thường truyền nguyên đối tượng `Throwable` thay vì chỉ `ex.getMessage()` để giữ stack trace và nhánh suppressed. **Đừng tự động dùng `ex.getSuppressed()[0]`** nếu chưa kiểm tra mảng có phần tử; trong một số đường chạy không có lỗi đóng nào nên mảng rỗng.

Không nên bắt rồi vứt bỏ lỗi khởi tạo chỉ vì dọn dẹp một tài nguyên đã thành công. Nếu lỗi khởi tạo khiến thao tác không thể tiếp tục, giữ nguyên nó hoặc bọc lại kèm cause, đồng thời ghi nhận lỗi đóng nếu có.

## 8. Giới hạn quan trọng: tài nguyên được cấp phát dở trong constructor

`try-with-resources` **chỉ tự động quản lý những resource expression đã hoàn tất bình thường**. Nếu một constructor hoặc factory bắt đầu cấp phát tài nguyên nội bộ, rồi ném trước khi trả về đối tượng cần quản lý, bên gọi **không nhận được tham chiếu đối tượng hoàn chỉnh** để đóng nó.

Ví dụ ý tưởng sai:

~~~java
// Mã minh họa hành vi nguy hiểm, không phải ví dụ độc lập.
class PartialResource implements AutoCloseable {
    private java.io.InputStream input;

    PartialResource(Path path) throws IOException {
        input = Files.newInputStream(path);  // Đã mở stream.
        validateHeader(input);               // Nếu ném IOException thì constructor thất bại.
    }

    @Override
    public void close() throws IOException {
        if (input != null) input.close();
    }
}
~~~

Nếu `validateHeader(input)` ném, việc tạo `new PartialResource(path)` **không hoàn tất bình thường**. Mặc dù lớp khai báo `close()`, `try (PartialResource r = new PartialResource(path))` ở bên ngoài **không tự gọi `r.close()`**, vì biến `r` chưa nhận đối tượng đã khởi tạo thành công. Nếu constructor không tự thu dọn stream, stream có thể bị rò rỉ.

Cách thiết kế tốt là đảm bảo constructor/factory **tự dọn những tài nguyên con nó đã cấp phát trước điểm thất bại**, hoặc xây dựng trong các phạm vi `try-with-resources` riêng. Ví dụ ý tưởng sửa:

~~~java
// Minh họa đặt trong lớp có Path, Files, InputStream và hàm validateHeader.
// ReturnedResource là lớp AutoCloseable nhận ownership của InputStream.
static ReturnedResource open(Path path) throws IOException {
    java.io.InputStream acquired = java.nio.file.Files.newInputStream(path);
    try {
        validateHeader(acquired);     // Có thể ném IOException.
        return new ReturnedResource(acquired);
    } catch (IOException | RuntimeException ex) {
        try {
            acquired.close();
        } catch (IOException closeFailure) {
            ex.addSuppressed(closeFailure);
        }
        throw ex;
    }
}
~~~

Đây là **đoạn minh họa không độc lập**, cần định nghĩa `ReturnedResource` và `validateHeader`; nó minh họa cách chuyển quyền sở hữu tài nguyên. Trong thiết kế trên, chỉ khi bước xác thực và tạo `ReturnedResource` thành công thì quyền đóng stream mới chuyển sang đối tượng kết quả; nếu xảy ra một `IOException` hoặc `RuntimeException` ở khối `try`, factory tự đóng stream và giữ lỗi đóng ở suppressed.

Phải định nghĩa rõ **điểm chuyển ownership** và tránh vừa factory vừa caller cùng chịu trách nhiệm đóng trên đường thành công. Tùy API, dùng factory riêng, các phạm vi `try-with-resources` lồng nhau hoặc đối tượng `AutoCloseable` có logic khởi tạo an toàn sẽ dễ kiểm soát hơn.

**Giới hạn của đoạn minh họa:** nó minh họa các ngoại lệ `IOException`/`RuntimeException` được bắt; đừng coi nó là cơ chế khôi phục tuyệt đối nếu JVM/process dừng cưỡng bức hoặc phát sinh lỗi nghiêm trọng khác. Tài nguyên cấp phát và sở hữu phải được thiết kế có chủ đích.

## 9. Resource expression là phương thức factory, không nhất thiết `new`

Danh sách tài nguyên có thể được khởi tạo bằng constructor hoặc một factory:

~~~java
try (BufferedReader reader = Files.newBufferedReader(path);
     InputStream input = Files.newInputStream(otherPath)) {
    // Dùng reader và input.
}
~~~

Nếu `Files.newBufferedReader(path)` trả về reader thành công còn `Files.newInputStream(otherPath)` ném `IOException`, Java gọi `reader.close()`. Nếu việc tạo reader ngay ở biểu thức đầu tiên thất bại, không có reader hoàn chỉnh thuộc danh sách để tự đóng.

Các `import` và biến `path`, `otherPath` trong đoạn minh họa cần được cung cấp ở phương thức bao ngoài. Điểm quan trọng không phụ thuộc vào việc biểu thức viết `new SomeResource()` hay `SomeFactory.open()`: **kết quả của biểu thức initializer có hoàn thành bình thường không** mới quyết định Java bắt đầu quản lý tài nguyên ấy.

Một factory tốt cần làm rõ: nếu factory ném ngoại lệ, nó có giữ lại tài nguyên nội bộ nào không? Nếu có, đó là lỗi quản lý ownership cần khắc phục trong factory, vì caller có thể không nhận được đối tượng để đóng.

## 10. Biến tài nguyên có sẵn từ Java 9: khác với lỗi trong header

Java 9 trở đi cho phép khai báo một biến tài nguyên **đã tồn tại** trong `try(...)` nếu biến đó là `final` hoặc *effectively final*:

~~~java
// Đoạn minh họa trong phương thức throws IOException.
java.io.InputStream in = java.nio.file.Files.newInputStream(path);

try (in) {
    System.out.println(in.read());
}
~~~

Trong ví dụ, `in` được tạo **trước khi bước vào cấu trúc `try-with-resources`**. Nếu lời gọi `Files.newInputStream(path)` ném, việc thực thi chưa đi đến `try (in)`, do đó `try (in)` không thể tự xử lý một tài nguyên chưa được tạo. Nếu thành công, `try (in)` sẽ đóng tài nguyên khi kết thúc phạm vi của nó.

Đây là một khác biệt đáng nhớ với cách viết mở tài nguyên **ngay trong header**:

~~~java
try (java.io.InputStream in = java.nio.file.Files.newInputStream(path)) {
    System.out.println(in.read());
}
~~~

Cách thứ hai đưa biểu thức mở tài nguyên trực tiếp vào vùng quản lý. Trong cả hai trường hợp, một lỗi xảy ra trước khi có một resource reference được khởi tạo thành công đều không làm Java gọi `close()` trên tài nguyên chưa được nhận về. Nhưng khi nhiều tài nguyên nằm trong header, Java sẽ dọn dẹp **những tài nguyên trước đó đã hoàn tất khởi tạo** nếu một biểu thức sau thất bại.

`effectively final` nghĩa là biến không được gán lại sau khi được gán giá trị, theo quy tắc của Java. Bạn không thể dùng một biến thường xuyên được gán lại trong cú pháp `try (in)` chỉ vì nó có kiểu `AutoCloseable`.

## 11. `catch` và `finally` nhận lỗi vào thời điểm nào?

Với cấu trúc mở rộng:

~~~java
try (Resource a = openA(); Resource b = openB()) {
    work(a, b);
} catch (IOException ex) {
    report(ex);
} finally {
    after();
}
~~~

Quy tắc ngữ nghĩa: khối dọn dẹp tài nguyên tự động chạy theo quy tắc `try-with-resources` **trước khi các nhánh `catch`/`finally` đi kèm được thực hiện**. Vì vậy `catch` có thể nhận một ngoại lệ chính đã mang suppressed exceptions từ bước đóng.

Nếu B khởi tạo thất bại:

~~~text
openA thành công
openB ném IOException
A.close chạy (có thể thêm suppressed)
catch (IOException ex) chạy
finally chạy
~~~

Nếu không có `catch` phù hợp, `finally` vẫn chạy khi cấu trúc bị rời, rồi ngoại lệ được truyền lên tầng gọi nếu `finally` hoàn tất bình thường.

Một cảnh báo khác: nếu chính `catch` hoặc `finally` đi kèm **ném ngoại lệ mới**, đường thoát của cấu trúc có thể thay đổi. Ví dụ `finally` viết thủ công ném lỗi khác có thể che cả lỗi khởi tạo B đã được lưu suppression. Vì vậy không nên thêm vào `finally` một thao tác có khả năng lỗi mà không xem xét cách xử lý/bảo toàn lỗi chính.

## 12. So sánh với `try/finally` thủ công

Trước Java 7, việc đóng một số tài nguyên thường viết bằng `finally`, chẳng hạn:

~~~java
// Minh họa không khuyến nghị cho tài nguyên AutoCloseable.
// Resource r = null đã được khai báo tại đây.
try {
    r = openResource();
    use(r);
} finally {
    if (r != null) {
        r.close();
    }
}
~~~

Khi chỉ quản lý một tài nguyên và tất cả thao tác thành công, cách này có thể hoạt động. Nhưng khi có **nhiều tài nguyên** và một tài nguyên ở giữa thất bại, bạn phải tự theo dõi những tài nguyên trước đó đã tạo thành công, đóng theo thứ tự phù hợp, bắt lỗi từ `close()` và bảo toàn lỗi chính.

Ví dụ thủ công với hai biến:

~~~java
// Mã khung minh họa; A/B đều AutoCloseable và các hàm có khai báo phù hợp.
A a = null;
B b = null;
try {
    a = openA();
    b = openB();
    work(a, b);
} finally {
    if (b != null) b.close();
    if (a != null) a.close();
}
~~~

Nhìn thoáng qua đã thấy rủi ro: nếu `b.close()` ném, **dòng `a.close()` có thể không được thực hiện**; nếu `work` hoặc `openB` đã ném, ngoại lệ từ `close()` có thể che lỗi ban đầu. Muốn viết đúng và bảo toàn tất cả thông tin cần nhiều mã xử lý phụ.

`try-with-resources` giúp loại bỏ những lỗi thủ công phổ biến đó, **nhưng không sửa được một constructor/factory cấp phát dở và không tự thu dọn phần tài nguyên nội bộ của chính nó khi thất bại**.

## 13. Checked exception và hợp đồng `close()`

`AutoCloseable.close()` khai báo `throws Exception`; các lớp con có thể thu hẹp kiểu ngoại lệ hoặc không ném checked exception. Chẳng hạn `Closeable.close()` khai báo `throws IOException`. Vì vậy khi viết `try-with-resources`, compiler xét cả:

- kiểu checked exception có thể được ném trong biểu thức khởi tạo tài nguyên;
- kiểu checked exception có thể phát sinh từ phần thân;
- kiểu checked exception mà `close()` của các tài nguyên có thể truyền ra.

Với ví dụ `ResourceInitFailureDemo`, cả constructor lẫn `close()` khai báo `throws IOException`, và `catch (IOException ex)` ở `main` là hợp lệ. Nếu bỏ `catch` đó và không khai báo `throws IOException` ở `main`, compiler sẽ báo lỗi do `IOException` có thể thoát ra.

Ví dụ chữ ký phương thức:

~~~java
// Đoạn minh họa đặt trong một lớp.
static void workWithResources() throws IOException {
    try (Resource a = openA(); Resource b = openB()) {
        doWork(a, b);
    }
}
~~~

Đoạn này **không độc lập**, phụ thuộc các kiểu/hàm được khai báo phù hợp. `throws IOException` thông báo khả năng lỗi, nhưng **không tự đóng tài nguyên** và không thay thế cấu trúc `try-with-resources`. Chính phần `try (...)` thực hiện quản lý tự động.

Đối với tài nguyên có `close()` khai báo `throws Exception`, phương thức bao ngoài có thể cần xử lý hoặc khai báo `Exception` (hay kiểu checked được suy luận cụ thể) nếu không có `catch` phù hợp. Không nên tùy tiện khai báo `throws Exception` cho mọi API; thiết kế tài nguyên với loại checked exception sát nghĩa sẽ giúp người dùng dễ xử lý hơn.

## 14. Quy tắc riêng khi có nhiều lỗi đóng tài nguyên

Khi một initializer hoặc body đã ném ngoại lệ chính, các lỗi từ việc đóng những tài nguyên đã khởi tạo thành công thường được **suppressed** vào ngoại lệ chính. Ví dụ:

~~~text
B khởi tạo lỗi          <- ngoại lệ chính
A.close lỗi            <- suppressed của lỗi B
~~~

Nếu **không có lỗi khởi tạo hoặc body** và trong lúc đóng có nhiều lỗi, ngoại lệ từ tài nguyên được đóng trước (theo thứ tự ngược khai báo) có thể trở thành **ngoại lệ chính**, còn lỗi từ các tài nguyên đóng sau là suppressed.

Ví dụ với thứ tự khai báo A, B, C và body hoàn tất:

~~~text
C.close lỗi            <- ngoại lệ chính lúc đóng
B.close lỗi            <- suppressed
A.close lỗi            <- suppressed
~~~

Cơ chế này giúp việc đóng những tài nguyên còn lại vẫn được thực hiện dù một lần đóng đã thất bại, đồng thời tránh bỏ mất các lỗi phụ. Nó không bảo đảm rằng thao tác đóng thành công; nó chỉ bảo toàn đường đi và thông tin lỗi theo quy tắc của Java.

Một số đối tượng `Throwable` tùy chỉnh có thể tắt tính năng suppression; trong tình huống đó `getSuppressed()` có thể không lưu lỗi phụ như trường hợp mặc định. Với `IOException` và `RuntimeException` được tạo thông thường, suppression được bật.

## 15. Phân biệt ba trường hợp dễ nhầm

### 15.1. Initializer ném exception

~~~java
try (Resource a = openA();
     Resource b = openB()) {
    work(a, b);
}
~~~

Nếu `openB()` ném: A được đóng, B không được coi là đã tạo thành công, body không chạy.

### 15.2. Initializer trả về `null`

~~~java
// Mã minh họa với phương thức maybeOpen() có thể trả null.
try (Resource a = maybeOpen()) {
    System.out.println("Đã vào body");
}
~~~

Nếu `maybeOpen()` **trả về `null` mà không ném**, body vẫn chạy và Java chỉ bỏ qua lệnh đóng `a` vì `a == null`. Nếu code body truy cập `a`, có thể phát sinh `NullPointerException`; đó là lỗi ở body, khác với lỗi initializer.

### 15.3. Constructor mở tài nguyên con rồi ném

~~~java
try (CompositeResource r = new CompositeResource(path)) {
    use(r);
}
~~~

Nếu constructor `CompositeResource` đã mở stream nội bộ rồi ném, `r` không được gán một đối tượng hoàn chỉnh, nên Java **không gọi `r.close()`**. Constructor/factory phải tự thu dọn những tài nguyên con nó đã cấp phát. Đây là nguyên nhân rò rỉ tài nguyên có thể xảy ra **dù caller có dùng `try-with-resources`**.

## 16. Checklist thiết kế và kiểm thử

Khi viết API mở tài nguyên hoặc đoạn `try-with-resources` có nhiều tài nguyên, hãy kiểm tra:

1. **Thứ tự mở/khởi tạo:** tài nguyên nào phụ thuộc tài nguyên trước? Thao tác mở có thể ném ngoại lệ gì?
2. **Ownership rõ ràng:** sau khi mở thành công, ai chịu trách nhiệm đóng? Nếu mở không hoàn tất, factory đã dọn phần được cấp phát chưa?
3. **Điểm thất bại ở từng initializer:** thử lỗi ở tài nguyên đầu, giữa và cuối; xác minh những tài nguyên trước đó được đóng ngược thứ tự.
4. **Phần thân không chạy khi khởi tạo chưa xong:** tránh kỳ vọng code trong body sẽ thực hiện bước rollback cho lỗi initializer.
5. **Lỗi trong `close()`:** kiểm tra lỗi chính và `getSuppressed()`, nhất là khi vừa mở tài nguyên sau bị lỗi vừa đóng tài nguyên trước bị lỗi.
6. **`catch` xử lý đúng kiểu:** lỗi từ initializer là checked/unchecked theo loại thực tế; handler phải có chiến lược xử lý hoặc truyền tiếp.
7. **`finally` của cấu trúc bên ngoài:** đảm bảo logic cleanup thêm không che lỗi chính hoặc ném ngoại lệ mới một cách vô ý.
8. **Không dùng GC/`finalize()` để chữa rò rỉ:** đóng chủ động và thiết kế đúng ownership mới là giải pháp.
9. **Không trả về đối tượng lỗi giả như một tài nguyên hợp lệ:** nếu factory dùng `null` báo thất bại, tài liệu phải làm rõ; tốt hơn là dùng API có hợp đồng minh bạch cho kết quả rỗng hoặc ném ngoại lệ.
10. **Báo lỗi đầy đủ:** log đối tượng ngoại lệ để giữ stack trace, cause và suppressed; không chỉ lưu thông điệp lỗi chính.

Nếu thiết kế có nhiều tài nguyên cần đóng, đưa chúng vào **cùng một `try-with-resources` hoặc các phạm vi lồng hợp lý** để Java quản lý cleanup. Đừng tự đóng lại các tài nguyên đã được cơ chế này quản lý nếu không có yêu cầu cụ thể và hiểu rõ hậu quả.

## 17. Những lỗi hiểu nhầm phổ biến

| Nhầm lẫn | Thực tế | Cách sửa |
| --- | --- | --- |
| B tạo thất bại nên A không được đóng vì body chưa chạy | Những tài nguyên đã khởi tạo trước đó vẫn được đóng. | Theo dõi thứ tự tạo và đóng ngược. |
| B constructor đã chạy một phần nên caller chắc chắn sẽ gọi `B.close()` | `B` chưa được tạo hoàn chỉnh; caller không có resource reference để đóng tự động. | Constructor/factory tự dọn tài nguyên con khi thất bại. |
| Nếu `openB()` lỗi, Java vẫn thử `openC()` | Đánh giá danh sách resource dừng tại điểm ném. | Không phụ thuộc vào side effect của các initializer phía sau. |
| Body có `finally` tự viết nên chắc chắn được thực hiện khi initializer lỗi | Nếu body chưa bắt đầu, những lệnh ở trong body không chạy. | Đặt cleanup tài nguyên cấp phát dở tại factory; dùng `try-with-resources`. |
| Lỗi `A.close()` thay thế lỗi khởi tạo B | `try-with-resources` thông thường lưu lỗi đóng dưới dạng suppressed của lỗi chính. | Xem `getSuppressed()`. |
| `catch` được chạy trước khi A được đóng | Các tài nguyên được đóng trước `catch` đi kèm. | Quan sát thứ tự log trong ví dụ. |
| Chỉ cần `try(r)` dù `r` được mở từ trước và mở thất bại | Khi mở trước `try` đã ném, cấu trúc `try` chưa bắt đầu. | Xử lý lỗi tại điểm mở hoặc mở trong resource header khi phù hợp. |
| Trả `null` từ initializer tương đương ném ngoại lệ | Trả `null` bình thường không ngăn body chạy; chỉ không gọi `close` lên `null`. | Thiết kế và kiểm tra hợp đồng factory rõ ràng. |
| `throws IOException` tự động dọn cleanup | `throws` chỉ công bố khả năng lỗi checked. | Dùng `try-with-resources` hoặc cleanup được quản lý. |
| Chỉ quan tâm lỗi khởi tạo, bỏ qua lỗi đóng | Có thể mất thông tin tài nguyên chưa đóng thành công. | Giữ stack trace/suppressed trong log và kiểm thử. |

## 18. Bài tập tự kiểm tra

**Câu 1.** `try (A a = openA(); B b = openB(); C c = openC())`: A thành công, B ném `IOException`. Java gọi những `close()` nào?

**Đáp án:** Gọi `a.close()`. Không gọi `b.close()` (B chưa tạo xong) hoặc `c.close()` (C chưa được tạo).

**Câu 2.** Khi B mở thất bại, thân `try` có chạy một vài lệnh đầu không?

**Đáp án:** Không. Toàn bộ danh sách tài nguyên phải khởi tạo bình thường rồi mới đến thân `try`.

**Câu 3.** A mở thành công, B mở lỗi, rồi A đóng cũng lỗi. Ngoại lệ nào được ưu tiên?

**Đáp án:** Lỗi từ B là ngoại lệ chính; lỗi đóng A được thêm vào suppressed của lỗi B trong trường hợp suppression thông thường.

**Câu 4.** Nếu C mở lỗi sau khi A và B đã mở thành công, thứ tự đóng là gì?

**Đáp án:** B rồi A.

**Câu 5.** `catch` gắn sau `try-with-resources` chạy trước hay sau `close()` của A/B?

**Đáp án:** Sau việc đóng các tài nguyên đã khởi tạo cần đóng.

**Câu 6.** Nếu ngay initializer của A lỗi, Java có gọi `A.close()` không?

**Đáp án:** Không, vì resource variable A chưa nhận được một đối tượng đã tạo thành công. Nếu constructor A tự cấp phát tài nguyên con, code trong constructor/factory phải tự xử lý phần ấy.

**Câu 7.** Nếu `openA()` trả về `null` nhưng không ném, body có chạy không?

**Đáp án:** Có thể chạy; Java không gọi `close()` đối với tham chiếu null.

**Câu 8.** `try (InputStream in = Files.newInputStream(path))` và `InputStream in = Files.newInputStream(path); try (in) { ... }` có cùng thời điểm mở stream không?

**Đáp án:** Không. Cách đầu mở trong resource header, cách sau mở trước khi vào cấu trúc `try (in)`. Cả hai đều quản lý tài nguyên đã mở thành công, nhưng vị trí phát sinh lỗi mở khác nhau.

**Câu 9.** Một constructor mở stream bên trong rồi ném trước khi trả đối tượng. Caller có thể chỉ trông vào `try-with-resources` để đóng stream ấy không?

**Đáp án:** Không; caller chưa sở hữu đối tượng được tạo hoàn chỉnh. Constructor/factory phải có chính sách cleanup khi thất bại.

**Câu 10.** Vì sao nên ghi log cả `getSuppressed()`?

**Đáp án:** Vì lỗi đóng tài nguyên xảy ra sau lỗi khởi tạo/body vẫn là thông tin quan trọng, dù không thay thế ngoại lệ chính.

## Tài liệu tham khảo

- [Java Language Specification 17 — §14.20.3, `try-with-resources`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): cú pháp và ngữ nghĩa toàn bộ cấu trúc.
- [Java Language Specification 17 — §14.20.3.1, Basic `try-with-resources`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3.1): mô hình xử lý khởi tạo, đóng tự động và suppressed exceptions.
- [Java Language Specification 17 — §14.20.3.2, Extended `try-with-resources`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3.2): mối quan hệ với `catch` và `finally` đi kèm.
- [Java SE 17 API — `AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng `close()`, kiểu ngoại lệ và cách dùng với `try-with-resources`.
- [Java SE 17 API — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getSuppressed()`, `addSuppressed()`, `getCause()`.
- [Oracle Java Tutorials — The `try-with-resources` Statement](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html): giải thích đóng tài nguyên và suppressed exceptions; ví dụ tutorial lịch sử, quy tắc nền tảng vẫn áp dụng trên Java 17.

**Ghi nhớ:** nếu **resource initializer ném ngoại lệ**, Java bỏ qua mọi initializer phía sau và phần thân `try`, nhưng vẫn **đóng các tài nguyên trước đó đã khởi tạo thành công theo thứ tự ngược**, giữ lỗi khởi tạo làm ngoại lệ chính và lưu lỗi đóng phụ qua suppressed exceptions. Riêng tài nguyên đang tạo dở bên trong constructor/factory phải được **chính nơi cấp phát quản lý an toàn**, vì caller không có đối tượng hoàn chỉnh để đóng.
