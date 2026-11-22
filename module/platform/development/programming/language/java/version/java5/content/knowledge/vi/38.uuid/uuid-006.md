# So sánh, equals và hashCode của UUID

Hai đối tượng `UUID` có thể được tạo ở hai thời điểm khác nhau nhưng cùng biểu diễn một định danh. Khi đó, câu hỏi “có cùng đối tượng không?” khác với “có cùng giá trị không?”, còn câu hỏi “đứng trước hay sau?” lại cần một quy tắc sắp xếp.

Bài này nối ba khái niệm đó với cách dùng UUID trong `HashMap`, `HashSet` và `TreeSet`. Các API được dùng vẫn áp dụng trong Java hiện đại; ví dụ có thể biên dịch bằng Java 17 trở lên.

## 1. Ba phép kiểm tra phục vụ ba mục đích

| Biểu thức | Câu hỏi được trả lời | Dùng khi |
| --- | --- | --- |
| `a == b` | Hai tham chiếu có trỏ tới cùng đối tượng? | Kiểm tra danh tính đối tượng khi thực sự cần |
| `a.equals(b)` | Hai UUID có cùng giá trị? | Đối chiếu định danh |
| `a.compareTo(b)` | a đứng trước, bằng hay sau b theo thứ tự tự nhiên của Java? | Sắp xếp, cây tìm kiếm |
| `a.hashCode()` | Mã băm của a là gì? | Hỗ trợ cấu trúc dữ liệu băm |

`hashCode` không trực tiếp trả lời hai UUID có bằng nhau hay không.

Một UUID chứa 128 bit và là bất biến. `equals` đối chiếu giá trị đầy đủ, không chỉ phiên bản, một nửa 64 bit hay một đoạn chuỗi. Hợp đồng các phương thức nằm trong tài liệu [UUID](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/UUID.html#equals(java.lang.Object)).

### Một tình huống thường gặp

Ứng dụng giữ một UUID trong bộ nhớ, còn yêu cầu HTTP gửi lại cùng UUID dưới dạng chuỗi. Sau khi phân tích chuỗi, giá trị được phục hồi có thể nằm trong một đối tượng khác.

Nếu dùng `==`, mã có thể kết luận sai rằng hai định danh khác nhau. Phép so đúng là `equals`.

Không cần đổi cả hai sang chuỗi để so sánh. Giữ kiểu `UUID` giúp tránh lẫn với một chuỗi bất kỳ và diễn đạt rõ rằng đang so giá trị định danh.

## 2. equals: bằng nhau theo toàn bộ giá trị

Với a và b khác null:

```text
a.equals(b)
    khi và chỉ khi
hai UUID có cùng toàn bộ 128 bit
```

Các tính chất cơ bản gồm:

- Một UUID bằng chính nó.
- Nếu a bằng b thì b bằng a.
- Nếu a bằng b và b bằng c thì a bằng c.
- `a.equals(null)` trả về `false`.
- `a.equals(a.toString())` trả về `false`: đối số là `String`, không phải `UUID`.

Một đối tượng có trường `id` cùng giá trị với UUID cũng không tự động bằng UUID đó. Phải chọn đúng thứ đang được so: định danh với định danh, hoặc thực thể với thực thể theo hợp đồng riêng.

### Khi một bên có thể null

Có thể dùng:

```java
// Đoạn biểu thức; cần import java.util.Objects.
boolean same = Objects.equals(firstId, secondId);
```

Quy tắc:

| firstId | secondId | Kết quả |
| --- | --- | --- |
| null | null | true |
| null | UUID khác null | false |
| UUID khác null | null | false |
| Hai UUID khác null | Theo `equals` |

Dùng `firstId.equals(secondId)` khi `firstId` có thể null sẽ gây `NullPointerException`. Nếu nghiệp vụ không cho phép thiếu định danh, nên kiểm tra và từ chối null tại ranh giới tạo hoặc nhận dữ liệu thay vì mặc nhiên xem hai giá trị thiếu là một định danh hợp lệ.

## 3. hashCode: hỗ trợ tìm kiếm, không thay thế định danh

`hashCode()` trả về `int`, chỉ có 32 bit. Không thể biểu diễn duy nhất mọi giá trị UUID 128 bit bằng một số 32 bit.

Hợp đồng quan trọng là:

```text
a.equals(b) == true
    => a.hashCode() == b.hashCode()
```

Chiều ngược lại **không đúng**:

```text
a.hashCode() == b.hashCode()
    không suy ra a.equals(b)
```

Hai giá trị khác nhau cùng mã băm được gọi là va chạm băm. Đây là tình huống cấu trúc băm phải xử lý, không phải một lỗi hợp đồng của UUID. Quy tắc chung được mô tả trong [Object.hashCode](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Object.html#hashCode()).

Khi tìm khóa trong cấu trúc băm, mã băm giúp thu hẹp ứng viên; so sánh giá trị vẫn quyết định khóa có khớp hay không. Vì thế không tự thay:

```java
// Minh họa cách sai khi muốn kiểm tra cùng UUID.
boolean same = first.hashCode() == second.hashCode();
```

bằng một “tối ưu” tương tự trong logic nghiệp vụ. Hãy dùng `first.equals(second)`.

### Vì sao UUID phù hợp làm khóa?

Giá trị UUID bất biến: sau khi đưa một UUID vào cấu trúc dữ liệu, các bit tham gia tính bằng nhau không đổi.

Hai đối tượng UUID bằng nhau sẽ tra cùng khóa trong `HashMap`. Tuy nhiên, nếu thay trường id của thực thể bằng một UUID mới, đó là **một khóa khác**, không phải cách đổi giá trị khóa đang được lưu trong map. Muốn thay khóa, phải thao tác rõ ràng trên map.

Không lưu `hashCode()` thay cho UUID trong cơ sở dữ liệu, URL hoặc thông điệp. Mã băm không giữ đủ thông tin để phục hồi UUID và không phải định danh duy nhất.

## 4. compareTo: thứ tự tự nhiên của Java

Kết quả được đọc theo dấu:

| Kết quả | Ý nghĩa |
| --- | --- |
| Nhỏ hơn 0 | a đứng trước b |
| Bằng 0 | a và b bằng nhau theo thứ tự so sánh |
| Lớn hơn 0 | a đứng sau b |

Với `UUID`, thứ tự tự nhiên nhất quán với `equals`:

```text
a.compareTo(b) == 0  <=>  a.equals(b)
```

Phải phân biệt thứ tự kỹ thuật với thứ tự thời gian tạo. Sắp các UUID ngẫu nhiên không cho biết bản ghi nào ra đời trước. Nếu muốn thứ tự ngày tạo, hãy dùng trường thời gian nghiệp vụ và quy tắc xử lý khi thời gian trùng.

### Chi tiết quan trọng: hai nửa long có dấu

Cách so sánh trong OpenJDK xét nửa 64 bit cao trước, rồi nửa 64 bit thấp nếu nửa cao bằng nhau. Mỗi nửa được so như `long` **có dấu**. Điều này được xác minh trong [mã nguồn UUID của OpenJDK 25](https://raw.githubusercontent.com/openjdk/jdk/jdk-25%2B36/src/java.base/share/classes/java/util/UUID.java).

Vì vậy không mặc nhiên coi `UUID.compareTo` là so một số nguyên không dấu 128 bit, hoặc là so chuỗi hệ 16 từ trái sang phải.

Ví dụ:

```text
left  = 7fffffff-ffff-4fff-8000-000000000000
right = 80000000-0000-4000-8000-000000000000
```

Nếu so chuỗi chuẩn cùng dạng chữ thường, `left` đứng trước `right` vì ký tự `7` đứng trước `8`.

Nhưng nửa cao của `right` có bit dấu bằng 1, nên khi hiểu như `long`, nó là số âm. Theo thứ tự Java, `right` đứng trước `left`.

Hai kết quả đều theo quy tắc đã chọn; lỗi xảy ra khi hai thành phần hệ thống chọn quy tắc khác nhau mà tưởng chúng tương đương.

## 5. Chương trình chạy đầy đủ

Lưu thành **UuidEqualityDemo.java**:

```java
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;
import java.util.UUID;

public class UuidEqualityDemo {
    static final Comparator<UUID> UNSIGNED_ORDER = (first, second) -> {
        int high = Long.compareUnsigned(
                first.getMostSignificantBits(),
                second.getMostSignificantBits());
        return high != 0 ? high : Long.compareUnsigned(
                first.getLeastSignificantBits(),
                second.getLeastSignificantBits());
    };

    public static void main(String[] args) {
        UUID first = UUID.fromString(
                "12345678-1234-4abc-8def-123456789abc");
        UUID copy = new UUID(first.getMostSignificantBits(),
                first.getLeastSignificantBits());

        System.out.println("same reference = " + (first == copy));
        System.out.println("same UUID = " + first.equals(copy));
        System.out.println("same hash = "
                + (first.hashCode() == copy.hashCode()));
        System.out.println("compare equal = " + first.compareTo(copy));
        System.out.println("equals text = " + first.equals(first.toString()));
        System.out.println("equals null = " + first.equals(null));
        System.out.println("both null = " + Objects.equals(null, null));

        Set<UUID> ids = new HashSet<>();
        ids.add(first);
        ids.add(copy);
        System.out.println("HashSet size = " + ids.size());

        Map<UUID, String> owners = new HashMap<>();
        owners.put(first, "Alice");
        System.out.println("lookup by equal UUID = " + owners.get(copy));

        UUID left = UUID.fromString(
                "7fffffff-ffff-4fff-8000-000000000000");
        UUID right = UUID.fromString(
                "80000000-0000-4000-8000-000000000000");
        System.out.println("natural left before right = "
                + (left.compareTo(right) < 0));
        System.out.println("text left before right = "
                + (left.toString().compareTo(right.toString()) < 0));
        System.out.println("unsigned left before right = "
                + (UNSIGNED_ORDER.compare(left, right) < 0));

        Set<UUID> naturalSet = new TreeSet<>();
        naturalSet.add(left);
        naturalSet.add(right);
        System.out.println("natural TreeSet size = " + naturalSet.size());

        Set<UUID> versionOnly = new TreeSet<>(
                Comparator.comparingInt(UUID::version));
        versionOnly.add(left);
        versionOnly.add(right);
        System.out.println("version-only TreeSet size = " + versionOnly.size());

        UUID collisionA = UUID.fromString(
                "00000000-0000-4000-8000-000000000000");
        UUID collisionB = UUID.fromString(
                "00000001-0000-4000-8000-000000000001");
        System.out.println("collision pair equal = "
                + collisionA.equals(collisionB));
        System.out.println("collision pair same hash = "
                + (collisionA.hashCode() == collisionB.hashCode()));

        Set<UUID> collisionSet = new HashSet<>();
        collisionSet.add(collisionA);
        collisionSet.add(collisionB);
        System.out.println("collision HashSet size = " + collisionSet.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 UuidEqualityDemo.java
java UuidEqualityDemo
```

Stdout:

```text
same reference = false
same UUID = true
same hash = true
compare equal = 0
equals text = false
equals null = false
both null = true
HashSet size = 1
lookup by equal UUID = Alice
natural left before right = false
text left before right = true
unsigned left before right = true
natural TreeSet size = 2
version-only TreeSet size = 1
collision pair equal = false
collision pair same hash = true
collision HashSet size = 2
```

`copy` được tạo bằng `new` để bảo đảm đây là đối tượng riêng. Vì hai nửa 64 bit được giữ nguyên, giá trị bằng `first`.

Hai UUID ở cuối được lựa chọn để minh họa va chạm với cách tính băm của OpenJDK đang dùng. Không xây dựng hợp đồng nghiệp vụ quanh một mã băm cụ thể hoặc quanh việc một cặp cố định luôn va chạm trên mọi cách cài đặt. Điều cần dựa vào là hợp đồng: bằng nhau phải cùng mã băm; khác nhau vẫn có thể cùng mã băm.

## 6. Vì sao HashSet giữ hai giá trị nhưng TreeSet có thể chỉ giữ một?

Trong chương trình:

- `HashSet` nhận hai đối tượng cùng giá trị `first` và `copy`, nên chỉ giữ một phần tử.
- `HashSet` nhận `collisionA` và `collisionB`, dù cùng mã băm nhưng khác giá trị, nên giữ hai phần tử.
- `TreeSet` theo thứ tự tự nhiên phân biệt `left` và `right`, nên giữ hai phần tử.
- `TreeSet` dùng bộ so sánh chỉ theo phiên bản xem cả hai UUIDv4 là ngang nhau, nên chỉ giữ một phần tử.

Trường hợp cuối là lỗi lựa chọn bộ so sánh nếu mục đích là lưu mọi UUID khác nhau.

`TreeSet` sử dụng kết quả so sánh để xác định hai phần tử có trùng theo thứ tự của tập hay không. Bộ so sánh cần nhất quán với `equals` để tập tuân theo hợp đồng `Set`. Xem [TreeSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeSet.html).

Nếu muốn nhóm theo phiên bản nhưng vẫn giữ mọi UUID khác nhau, bổ sung tiêu chí phân biệt đầy đủ:

```java
// Đoạn khai báo trong một lớp có import Comparator và UUID.
Comparator<UUID> byVersionThenValue =
        Comparator.comparingInt(UUID::version)
                .thenComparing(Comparator.naturalOrder());
```

Đừng dùng `hashCode` làm tiêu chí duy nhất cho `TreeSet`: các va chạm băm sẽ khiến hai UUID khác nhau bị xem là cùng phần tử.

## 7. Khi cần thứ tự không dấu hoặc thứ tự liên hệ thống

Bộ so sánh `UNSIGNED_ORDER` trong chương trình so nửa cao như số không dấu, rồi so nửa thấp như số không dấu. Đây là một **quy tắc ứng dụng lựa chọn rõ ràng**, khác với thứ tự tự nhiên của Java.

Nó trả 0 chỉ khi cả hai nửa bằng nhau, vì vậy vẫn nhất quán với `UUID.equals`.

Không viết bộ so sánh bằng cách trừ hai nửa rồi ép sang `int`:

```java
// Minh họa cách sai: có thể tràn số và làm mất bit khi ép kiểu.
int result = (int) (first.getMostSignificantBits()
        - second.getMostSignificantBits());
```

Ngay cả khi không tràn, hai nửa cao có thể bằng nhau trong khi nửa thấp khác nhau. Dùng `Long.compare` hoặc `Long.compareUnsigned` theo quy tắc đã chọn và xử lý cả hai nửa.

Khi phân trang hoặc sắp xếp qua nhiều thành phần, cần thống nhất:

1. Dữ liệu được so dưới dạng UUID, chuỗi hay 16 byte.
2. Mỗi phần số có được hiểu có dấu hay không dấu.
3. Nếu so văn bản, biểu diễn có được chuẩn hóa cùng độ dài và cùng cách viết chữ không.
4. Cơ sở dữ liệu và Java có thực sự dùng cùng quy tắc không.

Không suy ra thứ tự của cơ sở dữ liệu chỉ từ kết quả `UUID.compareTo`. Hãy kiểm tra hợp đồng và mẫu kiểm thử ở chính ranh giới lưu trữ, đặc biệt với các UUID bắt đầu bằng `7...` và `8...`.

## 8. Các lỗi cần nhận ra

| Lỗi | Hệ quả | Cách đúng |
| --- | --- | --- |
| So UUID bằng `==` | Hai đối tượng cùng định danh có thể bị xem là khác | Dùng `equals` |
| So UUID với chuỗi bằng `equals` | Luôn khác kiểu dù chữ trông giống | Phân tích chuỗi hoặc so đúng kiểu |
| Coi cùng `hashCode` là cùng UUID | Nhầm khi va chạm băm | So toàn bộ giá trị |
| Chỉ dùng nửa cao hoặc nửa thấp để so bằng | Bỏ qua 64 bit còn lại | Dùng `UUID.equals` |
| Coi thứ tự Java là thứ tự hệ 16 không dấu | Sai ở ranh giới bit dấu | Chọn và thống nhất quy tắc |
| Dùng so sánh UUIDv4 để suy ngày tạo | Thứ tự không mang ý nghĩa thời gian | Dùng trường thời gian riêng |
| Comparator chỉ xét phiên bản | `TreeSet` có thể bỏ UUID khác nhau | Thêm tiêu chí đầy đủ |
| Dùng phép trừ rồi ép kiểu để so | Tràn số hoặc mất thông tin | Dùng các hàm compare phù hợp |

Nếu chỉ cần kiểm tra cùng định danh, `equals` là biểu thức trực tiếp nhất. Thêm so chuỗi, tự tách trường hoặc tính băm không làm kiểm tra đó chính xác hơn.

## 9. Thực hành

1. Tạo hai đối tượng UUID có cùng giá trị bằng constructor hai `long`. Dự đoán kết quả `==`, `equals`, `hashCode` và `compareTo`.
2. Đưa hai UUID khác nhau cùng mã băm vào `HashMap`, gán hai giá trị khác nhau và xác nhận tra cứu đúng từng khóa.
3. Sửa `versionOnly` bằng `thenComparing`; xác nhận kích thước từ 1 thành 2.
4. Sắp cùng danh sách theo thứ tự tự nhiên và `UNSIGNED_ORDER`. Tìm cặp khác vị trí và giải thích bằng bit dấu.
5. Nêu vì sao hai UUID có cùng phiên bản và cùng bố cục vẫn chưa đủ để kết luận bằng nhau.

Kết quả cần đạt là phân biệt rõ **danh tính đối tượng**, **giá trị định danh**, **mã băm** và **quy tắc thứ tự**, rồi chọn đúng phép toán cho từng cấu trúc dữ liệu.
