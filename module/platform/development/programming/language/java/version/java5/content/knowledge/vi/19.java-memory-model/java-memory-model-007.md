# Ngữ nghĩa trường final sau khi hàm tạo hoàn tất

## 1. final có ý nghĩa về bộ nhớ, không chỉ về phép gán

Với một trường instance final, Java không chỉ hạn chế việc gán lại trong mã nguồn thông thường. Mô hình bộ nhớ còn có quy tắc giúp luồng khác nhìn thấy giá trị đã được khởi tạo đúng khi đối tượng được xây dựng đúng cách.

Mô hình sử dụng cần nhớ:

1. Khởi tạo các trường final trong quá trình xây dựng đối tượng.
2. Không để luồng khác lấy tham chiếu tới đối tượng đang được xây dựng.
3. Chỉ công bố đối tượng sau khi việc xây dựng đã hoàn tất.

Khi đáp ứng điều kiện này và luồng khác nhìn thấy đối tượng, các trường final được bảo đảm có giá trị khởi tạo đúng, thay vì giá trị mặc định ban đầu. [JLS §17.5](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.5)

Điều đó không đồng nghĩa “mọi lớp có một trường final đều an toàn theo luồng”. Còn phải xét cách chia sẻ tham chiếu, dữ liệu có thể thay đổi và những thao tác sau khi xây dựng.

## 2. Ba bảo đảm khác nhau

| Vấn đề | final có tự giải quyết hoàn toàn không? |
| --- | --- |
| Trường có được gán lại bằng mã Java thông thường không? | Hạn chế gán lại theo quy tắc final |
| Giá trị khởi tạo của trường final có được thấy đúng khi dùng đúng mô hình xây dựng không? | Có bảo đảm đặc biệt |
| Luồng khác có chắc nhận được tham chiếu mới đúng lúc không? | Không |
| Đối tượng được trường final tham chiếu có bất biến không? | Không tự động |
| Các cập nhật sau constructor có được đồng bộ hóa không? | Không |
| Một thao tác gồm nhiều bước có nguyên tử không? | Không |

Với trường tham chiếu final, không gán lại tham chiếu không đồng nghĩa không sửa được đối tượng phía sau nó. [JLS: trường final](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.3.1.2)

## 3. Hành động đóng băng khi constructor kết thúc

JLS mô tả một **hành động đóng băng (freeze action)** gắn với trường final khi constructor ghi trường đó kết thúc. Đây là khái niệm của mô hình bộ nhớ, không phải lời gọi API mà lập trình viên phải chèn vào mã.

Tên “đóng băng” không có nghĩa biến toàn bộ đồ thị đối tượng thành chỉ đọc. Nó nói về bảo đảm quan sát trạng thái khởi tạo của trường final và những truy cập liên quan theo quy tắc mô hình bộ nhớ.

Cách dùng an toàn cho người viết lớp là hoàn thành khởi tạo rồi mới chia sẻ đối tượng. Tránh suy luận quy tắc bộ nhớ từ giả định máy luôn ghi các trường ra bộ nhớ đúng thứ tự mà mắt ta đọc trong mã nguồn.

## 4. Vì sao phải tránh this thoát ra trong constructor?

Tham chiếu this có thể bị lộ qua:

- Gán vào một biến dùng chung.
- Đăng ký listener/callback với một đối tượng bên ngoài.
- Khởi động một luồng hoặc tác vụ có thể dùng this trước khi constructor kết thúc.
- Gọi mã có thể ghi đè ở lớp con và để mã đó công bố đối tượng đang xây dựng.

Ngay cả khi các phép gán final trông như đã nằm trước bước đăng ký, công bố ngay trong constructor vẫn không theo mô hình sử dụng “chỉ chia sẻ sau khi constructor hoàn tất”. [JSR-133 FAQ: xây dựng đúng đối tượng](https://www.cs.umd.edu/~pugh/java/memoryModel/jsr-133-faq.html)

### Ví dụ quan sát quá sớm, chạy được mà không cần đua thời điểm

Lưu thành **EarlyObservationDemo.java**:

```java
import java.util.function.Consumer;

public class EarlyObservationDemo {
    static final class Value {
        private final int id;

        Value(Consumer<Value> callback) {
            callback.accept(this);
            id = 42;
        }

        int id() {
            return id;
        }
    }

    public static void main(String[] args) {
        Value value = new Value(current ->
                System.out.println("during=" + current.id()));

        System.out.println("after=" + value.id());
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 EarlyObservationDemo.java
java EarlyObservationDemo
```

Kết quả:

```text
during=0
after=42
```

Đây là thiết kế **cố ý cho callback thấy đối tượng chưa hoàn tất**. Việc gọi phương thức id() gián tiếp đọc trường trước phép gán, nên đọc giá trị mặc định 0. Không có phép gán lại final nào xảy ra; constructor chỉ gán id sau callback.

Ví dụ chạy một luồng để làm rõ lỗi vòng đời đối tượng, không phải để chứng minh một kết quả data race cụ thể. Nếu callback chuyển đối tượng sang luồng khác, việc suy luận còn phải xét mô hình bộ nhớ và công bố tham chiếu.

Cách sửa thiết kế là hoàn thành `new Value(...)` trước, rồi mới đăng ký hay gọi mã bên ngoài bằng đối tượng hoàn chỉnh; không cố chữa bằng việc thêm sleep trong constructor.

## 5. Trường final tham chiếu mảng: trạng thái khởi tạo khác với sửa đổi về sau

Giả sử constructor tạo mảng và gán tham chiếu vào trường final. Bảo đảm khởi tạo có thể áp dụng tới trạng thái mảng được thiết lập trước khi constructor hoàn tất khi đọc qua đường tham chiếu final phù hợp.

Nhưng sau đó, nếu một luồng sửa `array[0]`, phần tử mảng không trở thành final theo. Cần chính sách riêng cho các cập nhật đó. “Nhìn thấy trạng thái lúc xây dựng” không có nghĩa “tự thấy mọi thay đổi mới nhất sau này”. [JSR-133 FAQ: trường final tham chiếu đối tượng](https://www.cs.umd.edu/~pugh/java/memoryModel/jsr-133-faq.html)

Đoạn đơn giản sau minh họa sự khác biệt, đặt trong một phương thức:

```java
final int[] numbers = {1, 2};
numbers[0] = 9;          // Legal: changes array content.
// numbers = new int[2]; // Illegal: reassigns the final reference.
```

Vì vậy, để tạo một đối tượng bất biến thực sự, cần kiểm soát quyền sở hữu dữ liệu có thể sửa: sao chép đầu vào và không trả mảng nội bộ cho bên gọi. Đây là lựa chọn thiết kế của lớp, không phải tác dụng tự động của từ khóa final. [Oracle: chiến lược đối tượng bất biến](https://docs.oracle.com/javase/tutorial/essential/concurrency/imstrat.html)

## 6. Chương trình dùng snapshot bất biến và công bố qua Future

Chương trình sau dùng các trường final, sao chép mảng ở ranh giới và chuyển kết quả từ tác vụ sang luồng chính qua Future.

Lưu thành **FinalSnapshotDemo.java**:

```java
import java.util.Arrays;
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FinalSnapshotDemo {
    static final class Settings {
        private final String name;
        private final int port;
        private final int[] limits;

        Settings(String name, int port, int[] limits) {
            this.name = Objects.requireNonNull(name, "name");

            if (port < 1 || port > 65535) {
                throw new IllegalArgumentException(
                        "port is out of range");
            }
            this.port = port;

            Objects.requireNonNull(limits, "limits");
            this.limits = Arrays.copyOf(limits, limits.length);
        }

        String name() {
            return name;
        }

        int port() {
            return port;
        }

        int[] limits() {
            return Arrays.copyOf(limits, limits.length);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        try {
            Future<Settings> future = executor.submit(() -> {
                int[] input = {3, 5};
                Settings settings =
                        new Settings("production", 8080, input);

                input[0] = 99;
                return settings;
            });

            Settings snapshot = future.get();

            System.out.println("name=" + snapshot.name());
            System.out.println("port=" + snapshot.port());
            System.out.println("limits="
                    + Arrays.toString(snapshot.limits()));

            int[] externalCopy = snapshot.limits();
            externalCopy[0] = 77;

            System.out.println("afterExternalChange="
                    + Arrays.toString(snapshot.limits()));
        } finally {
            executor.shutdown();
        }
    }
}
```

Chạy:

```shell
javac --release 17 -encoding UTF-8 FinalSnapshotDemo.java
java FinalSnapshotDemo
```

Kết quả:

```text
name=production
port=8080
limits=[3, 5]
afterExternalChange=[3, 5]
```

### Mỗi cơ chế chịu trách nhiệm cho điều gì?

- final giúp xác định trạng thái khởi tạo và hạn chế gán lại các trường.
- Constructor không chuyển this cho bên khác trong lúc xây dựng.
- Bản sao mảng đầu vào ngăn bên giữ input sửa trạng thái Settings.
- Bản sao ở getter ngăn bên nhận kết quả sửa mảng nội bộ.
- Settings là lớp final, không cho lớp con tùy ý phá cách cung cấp trạng thái.
- Future.get cung cấp cơ chế chuyển kết quả giữa các luồng theo hợp đồng nhất quán bộ nhớ.

Các hành động trong tác vụ xảy ra trước khi bên khác lấy kết quả thành công qua Future.get theo hợp đồng của thư viện concurrent. Vì vậy chương trình này minh họa một thiết kế hoàn chỉnh dùng được, **không phải phép thử tách riêng bảo đảm của final**: Future còn công bố an toàn cả dữ liệu thường được thiết lập trước khi hoàn thành tác vụ. [Hợp đồng nhất quán bộ nhớ concurrent](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/package-summary.html)

`Arrays.copyOf` tạo mảng mới với nội dung được sao chép. Với int[], các phần tử là giá trị nguyên thủy; nếu dùng mảng đối tượng có thể sửa, bản sao mảng không tự sao chép sâu các đối tượng phần tử. [API Arrays.copyOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html#copyOf(int%5B%5D,int))

## 7. final không thay việc công bố tham chiếu

Có thể minh họa bằng cấu trúc sau, chưa phải chương trình chạy đầy đủ:

```java
final class Pair {
    final int stable;
    int ordinary;

    Pair() {
        stable = 17;
        ordinary = 29;
    }
}
```

Giả sử một luồng tạo Pair rồi gán tham chiếu vào một biến dùng chung thông thường; không có this thoát trong constructor và không có sửa đổi tiếp theo. Luồng khác nếu lấy được tham chiếu được công bố sau khi constructor kết thúc thì có bảo đảm stable là 17 trong thiết lập này. Không có bảo đảm tương tự rằng ordinary phải là 29; đọc ordinary có thể thấy giá trị mặc định 0 nếu thiếu đồng bộ cần thiết.

Tuy nhiên, final không bảo đảm vòng chờ trên một biến tham chiếu thường sẽ kết thúc, không bảo đảm lúc nào luồng khác nhận tham chiếu mới, và không tự biến đường chia sẻ đó thành một giao thức đồng bộ tốt. Không dùng việc nhìn thấy final đúng làm lý do giữ một vòng chờ không đồng bộ.

Trong mã ứng dụng, hãy vẫn chọn cơ chế công bố rõ ràng: biến volatile cho snapshot, cùng khóa khi đọc/ghi, khởi tạo static hoặc công cụ concurrent phù hợp. Một đối tượng bất biến giúp giảm nhu cầu bảo vệ **trạng thái bên trong**, chứ không tự thiết kế toàn bộ quy trình truyền nó giữa các luồng. [Oracle: đối tượng bất biến](https://docs.oracle.com/javase/tutorial/essential/concurrency/immutable.html)

Nếu dùng volatile để công bố snapshot mới, bên đọc có thể lấy tham chiếu vào một biến cục bộ rồi dùng nhất quán snapshot đó cho một thao tác. Đọc lại nhiều lần tham chiếu chung trong cùng một phép xử lý có thể trộn các phiên bản snapshot khi bên ghi đang thay thế chúng.

## 8. Những giới hạn cần hiểu

### Chỉ có final trên tham chiếu không đủ

Một `final List` vẫn có thể bị thêm/xóa phần tử nếu đối tượng List cho phép. Một record chứa mảng cũng không tự tạo bản sao mảng. Cần kiểm tra toàn bộ trạng thái quan sát được của đối tượng nếu muốn công bố nó là bất biến.

### Constructor lớp cha xong chưa có nghĩa toàn bộ lớp con đã xong

Việc khởi tạo đi qua nhiều constructor. Không công bố this từ constructor cha chỉ vì các trường của cha đã được gán: trạng thái riêng của lớp con vẫn có thể chưa được thiết lập.

### Trạng thái có thể sửa cần giao thức riêng

Nếu một đối tượng có cả final id và số dư có thể đổi, id không làm thao tác cập nhật số dư an toàn. Cần khóa, atomic hoặc chính sách sở hữu dữ liệu thích hợp cho phần trạng thái đó.

### Không dựa vào sửa final sau xây dựng

Bài hướng tới final trong mô hình xây dựng thông thường. Không dùng cơ chế can thiệp trường final sau constructor như cách cập nhật trạng thái ứng dụng; nó phá giả định thiết kế và không phải cơ chế công bố snapshot mới.

### Không chứng minh mô hình bộ nhớ bằng một lần chạy

Thử nghiệm chia sẻ không đồng bộ có thể tình cờ luôn thấy giá trị mong muốn trên máy hiện tại. Điều đó không nâng một hành vi quan sát được thành bảo đảm của Java. Ngược lại, các chương trình trong bài có stdout cố định vì chúng được thiết kế với thứ tự thực thi và cơ chế công bố rõ ràng.

### Tự kiểm tra

1. Trong EarlyObservationDemo, chuyển callback ra sau khi đối tượng được tạo xong. Kết quả quan sát thay đổi thế nào?
2. Bỏ bản sao mảng đầu vào trong Settings. Dòng `input[0] = 99` có thể làm thay đổi trạng thái nào?
3. Giữ bản sao đầu vào nhưng trả thẳng limits ở getter. Vì sao sửa externalCopy làm hỏng tính bất biến?
4. Nếu đổi port thành trường thường trong chương trình Future, Future.get vẫn có vai trò gì? Vì sao đó không phải phép thử chỉ dành cho final?
5. Thêm một trường có thể cập nhật sau constructor. Cần cơ chế nào để các cập nhật mới được quan sát đúng?
6. Giải thích bằng lời của bạn ba khái niệm: xây dựng đúng đối tượng, công bố tham chiếu và bất biến sau xây dựng.
