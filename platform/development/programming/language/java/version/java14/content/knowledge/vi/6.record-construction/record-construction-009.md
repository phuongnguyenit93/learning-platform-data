# Ngoại lệ khi khởi tạo record và cách giữ bất biến của đối tượng (Java 16+)

## 1. Đề bài: record ngắn gọn, nhưng ai bảo đảm dữ liệu hợp lệ?

`record` phù hợp để mô tả một bộ dữ liệu có cấu trúc rõ ràng. Ví dụ:

```java
public record DateRange(java.time.LocalDate from,
                        java.time.LocalDate to) {}
```

Record này đã có canonical constructor, accessor `from()`/`to()`, `equals()`, `hashCode()` và `toString()`. Tuy nhiên, **record không tự kiểm tra các quy tắc nghiệp vụ**: đoạn trên vẫn cho phép `from` hoặc `to` là `null`, hoặc `to` đứng trước `from`. Hơn nữa, các trường component chỉ là **`final` ở mức tham chiếu**: nếu một component trỏ tới danh sách hay đối tượng mutable, dữ liệu có thể vẫn thay đổi.

Để dùng record an toàn, cần xác định và bảo vệ **bất biến (invariant)** của đối tượng: các điều kiện phải đúng với mọi đối tượng *được tạo thành công* và vẫn đúng trong suốt thời gian sử dụng.

Ví dụ, một record biểu diễn kỳ lưu trú có thể có các invariant:

1. Mã đặt chỗ `bookingId` phải khác `null` và không rỗng sau khi chuẩn hóa.
2. `checkIn` và `checkOut` phải khác `null`; ngày trả phòng phải sau ngày nhận phòng.
3. `guestNames` phải có ít nhất một tên khách, không chứa `null` hoặc tên trống.
4. Danh sách khách lưu trong record không được thay đổi khi bên gọi sửa danh sách đầu vào hoặc cố sửa danh sách trả về bởi accessor.

**Trách nhiệm bảo vệ invariant đặt trong canonical constructor**. Nếu đầu vào không hợp lệ, constructor **ném ngoại lệ** để `new` không trả về một đối tượng vi phạm invariant. Nếu đầu vào hợp lệ, constructor kiểm tra, có thể chuẩn hóa và tạo bản sao phòng vệ trước khi lưu.

> **Mốc phiên bản:** Record từng là tính năng preview ở Java 14/15, đã chính thức từ **Java 16** theo [JEP 395](https://openjdk.org/jeps/395). Các ví dụ trong bài dùng **cú pháp record chính thức Java 16+**, vẫn được hỗ trợ trong Java hiện đại; không yêu cầu `--enable-preview`.

## 2. Constructor record và cơ chế xử lý ngoại lệ

Một record có **canonical constructor** tương ứng với đầy đủ các component. Với `record DateRange(LocalDate from, LocalDate to)`, tham số constructor chuẩn có kiểu và thứ tự tương ứng là `from` và `to`.

Khi muốn kiểm tra đầu vào, cách viết thường ngắn gọn nhất là **compact canonical constructor**:

```java
import java.time.LocalDate;
import java.util.Objects;

public record DateRange(LocalDate from, LocalDate to) {
    public DateRange {
        Objects.requireNonNull(from, "from");
        Objects.requireNonNull(to, "to");
        if (to.isBefore(from)) {
            throw new IllegalArgumentException(
                    "to không được trước from");
        }
    }
}
```

Đây là một **tệp độc lập `DateRange.java`**. Constructor có tên `DateRange` nhưng **không viết lại danh sách tham số**. Java hiểu ngầm các tham số `from` và `to` từ header record. Compiler sẽ gán các tham số hợp lệ vào các trường `final` tương ứng **sau khi thân compact constructor kết thúc bình thường**.

Quy trình logic:

```text
Bên gọi tính các đối số của new DateRange(...)
      |
      v
Compact canonical constructor nhận tham số from/to
      |
      +-- Kiểm tra null, quan hệ ngày, điều kiện nghiệp vụ
      |      |
      |      +-- Nếu sai: throw -> new không trả về đối tượng
      |      |
      |      +-- Nếu đúng: kết thúc thân constructor
      |
      v
Compiler tự gán tham số vào component fields
      |
      v
Biểu thức new hoàn tất và trả về đối tượng hợp lệ
```

**Không được gán `this.from = from` hoặc `this.to = to` trong compact constructor.** Gán trực tiếp vào component field tại đây gây lỗi biên dịch. Thay vào đó, có thể **gán lại tham số** để chuẩn hóa trước khi compiler tự lưu.

### Dùng loại ngoại lệ phù hợp

| Trường hợp | Ngoại lệ thường dùng | Ý nghĩa |
| --- | --- | --- |
| Bắt buộc có đối số nhưng nhận `null` | `NullPointerException` qua `Objects.requireNonNull(...)` | Báo thiếu một tham chiếu bắt buộc |
| Có giá trị nhưng vi phạm ràng buộc, chẳng hạn ngày kết thúc trước ngày bắt đầu | `IllegalArgumentException` | Đối số không hợp lệ về mặt nghiệp vụ |
| Danh sách có phần tử `null` và dùng `List.copyOf(...)` | `NullPointerException` | `List.copyOf` không chấp nhận phần tử `null` |
| Gọi `add`/`remove` trên danh sách không thể thay đổi do `List.copyOf` cung cấp | `UnsupportedOperationException` | Lỗi của bên **sử dụng** cố chỉnh sửa danh sách sau tạo, không phải lỗi constructor |
| Lỗi I/O hoặc dịch vụ trong lúc tính dữ liệu bên ngoài record | Ngoại lệ theo API đó | Không đồng nghĩa với việc compiler tự có cơ chế rollback |

**Không phải cứ input sai là bắt buộc dùng cùng một loại exception.** Hãy chọn quy ước ổn định cho API, có thông điệp hữu ích, và phân biệt lỗi đầu vào của caller với sự cố hệ thống. Nếu API cần báo lỗi người dùng bằng cấu trúc thay vì ném exception, có thể dùng **factory/service** để trả về kết quả validation; canonical constructor vẫn nên ngăn mọi cách tạo record trái invariant.

## 3. Ví dụ hoàn chỉnh: phát hiện lỗi, sao chép dữ liệu và giữ trạng thái

Tạo tệp **`RecordInvariantDemo.java`**:

```java
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class RecordInvariantDemo {
    public record Stay(
            String bookingId,
            LocalDate checkIn,
            LocalDate checkOut,
            List<String> guestNames) {

        // Canonical constructor dạng compact:
        // kiểm tra/chuẩn hóa trước khi các component được gán.
        public Stay {
            bookingId = Objects.requireNonNull(bookingId, "bookingId").strip();
            if (bookingId.isEmpty()) {
                throw new IllegalArgumentException("bookingId rỗng");
            }

            Objects.requireNonNull(checkIn, "checkIn");
            Objects.requireNonNull(checkOut, "checkOut");
            if (!checkOut.isAfter(checkIn)) {
                throw new IllegalArgumentException("checkOut phải sau checkIn");
            }

            // Chụp bản sao danh sách đầu vào; List.copyOf từ chối null.
            guestNames = List.copyOf(
                    Objects.requireNonNull(guestNames, "guestNames"));
            if (guestNames.isEmpty()) {
                throw new IllegalArgumentException("phải có khách");
            }
            for (String name : guestNames) {
                if (name.isBlank()) {
                    throw new IllegalArgumentException("tên khách rỗng");
                }
            }
        }

        // Thay đổi dữ liệu bằng một đối tượng mới, vẫn qua validation.
        public Stay withGuestNames(List<String> replacement) {
            return new Stay(bookingId, checkIn, checkOut, replacement);
        }
    }

    public static void main(String[] args) {
        List<String> submitted = new ArrayList<>(List.of("An", "Bình"));
        Stay original = new Stay(
                "  BK-42  ",
                LocalDate.of(2026, 11, 10),
                LocalDate.of(2026, 11, 12),
                submitted);
        submitted.add("Chi");

        System.out.println(original.bookingId());
        System.out.println(original.guestNames());

        try {
            original.guestNames().add("Dũng");
        } catch (UnsupportedOperationException e) {
            System.out.println("Không sửa được danh sách của record");
        }

        Stay updated = original.withGuestNames(List.of("An", "Chi"));
        System.out.println(original.guestNames());
        System.out.println(updated.guestNames());

        try {
            new Stay(
                    "BK-43",
                    LocalDate.of(2026, 11, 15),
                    LocalDate.of(2026, 11, 15),
                    List.of("An"));
        } catch (IllegalArgumentException e) {
            System.out.println("Bị từ chối: " + e.getMessage());
        }

        try {
            new Stay(
                    null,
                    LocalDate.of(2026, 11, 15),
                    LocalDate.of(2026, 11, 16),
                    List.of("An"));
        } catch (NullPointerException e) {
            System.out.println("Thiếu dữ liệu: " + e.getMessage());
        }

        try {
            new Stay(
                    "BK-44",
                    LocalDate.of(2026, 11, 15),
                    LocalDate.of(2026, 11, 16),
                    Arrays.asList("An", null));
        } catch (NullPointerException e) {
            System.out.println("Danh sách có phần tử null");
        }
    }
}
```

Biên dịch và chạy bằng JDK 16 trở lên:

```bash
javac --release 16 -encoding UTF-8 RecordInvariantDemo.java
java RecordInvariantDemo
```

Cú pháp chạy này **không cần preview flag**. `--release 16` bảo đảm mã được kiểm tra theo ngôn ngữ và API chuẩn tương thích Java 16 khi dùng một `javac` đủ mới.

**Kết quả chạy chính xác:**

```text
BK-42
[An, Bình]
Không sửa được danh sách của record
[An, Bình]
[An, Chi]
Bị từ chối: checkOut phải sau checkIn
Thiếu dữ liệu: bookingId
Danh sách có phần tử null
```

### Diễn giải kết quả

1. Chuỗi `"  BK-42  "` được `strip()` thành `"BK-42"` **trong tham số constructor** trước khi compiler gán vào trường. Sau khi tạo thành công, accessor `bookingId()` trả `BK-42`.
2. `guestNames = List.copyOf(...)` bảo vệ danh sách bên trong. Sau khi gọi constructor, việc thêm `"Chi"` vào danh sách `submitted` của bên gọi **không ảnh hưởng** danh sách record; kết quả vẫn `[An, Bình]`.
3. `original.guestNames().add("Dũng")` ném `UnsupportedOperationException` vì danh sách trả về không hỗ trợ sửa cấu trúc. Đối tượng `original` vẫn hợp lệ và không bị thay đổi.
4. `withGuestNames(...)` tạo `Stay` mới qua canonical constructor. `original` giữ `[An, Bình]`, còn `updated` có `[An, Chi]`. Bất biến được **kiểm tra lại** cho trạng thái mới.
5. Ngày trả phòng bằng ngày nhận phòng làm `!checkOut.isAfter(checkIn)` thành `true`, nên `IllegalArgumentException` được ném và lần gọi `new Stay(...)` đó **không trả về record mới**.
6. `bookingId` bằng `null` bị `Objects.requireNonNull(..., "bookingId")` từ chối bằng `NullPointerException`; phần thông báo là `bookingId`.
7. Danh sách chứa một phần tử `null` bị `List.copyOf` từ chối. Ví dụ dùng `Arrays.asList("An", null)` để tạo đầu vào đó, vì bản thân `List.of` cũng không chấp nhận `null`.

## 4. Khi constructor ném ngoại lệ, đối tượng có bị tạo “nửa vời” không?

Với lời gọi:

```java
Stay bad = new Stay(
        "BK-99",
        LocalDate.of(2026, 12, 5),
        LocalDate.of(2026, 12, 2),
        List.of("An"));
```

Lời gọi constructor ném `IllegalArgumentException`. Khi không bắt ngoại lệ, phép gán cho `bad` **không hoàn tất** và luồng điều khiển dừng hoặc được truyền tới nơi xử lý exception. Không có `Stay` *được tạo thành công* nào với khoảng ngày sai được trả về từ biểu thức `new`.

Nếu muốn xử lý ngay tại điểm gọi, dùng `try/catch` với hành động có ý nghĩa:

```java
// Minh họa: đoạn nằm trong một phương thức.
try {
    Stay stay = new Stay(
            "BK-99",
            LocalDate.of(2026, 12, 5),
            LocalDate.of(2026, 12, 2),
            List.of("An"));
    System.out.println(stay.bookingId());
} catch (IllegalArgumentException ex) {
    System.out.println("Dữ liệu đặt chỗ không hợp lệ: " + ex.getMessage());
}
```

Nhánh in `stay.bookingId()` sẽ không chạy khi constructor ném. **Không bắt exception bên trong constructor rồi tiếp tục như thể dữ liệu hợp lệ** nếu chưa sửa được nguyên nhân; làm vậy có thể cho phép trạng thái sai đi qua.

**Phân biệt với rollback giao dịch:** ngoại lệ của constructor **không tự hoàn tác** tác dụng phụ đã xảy ra ở ngoài hoặc trong lúc tính đối số, ví dụ đã ghi file, gửi request, trừ tiền hoặc thay đổi một danh sách bên ngoài. Vì vậy, nên giữ validation/normalization của record **ít tác dụng phụ**, không gọi mạng hay cập nhật database trong constructor và xử lý giao dịch ở service khi có nhiều bước nghiệp vụ.

Đừng để tham chiếu tới đối tượng đang khởi tạo **thoát ra ngoài** trước khi constructor hoàn thành, chẳng hạn thông qua callback hoặc đăng ký vào một registry trong constructor. Điều này phá vỡ lý do ta muốn record chỉ được quan sát khi các invariant đã được thiết lập.

## 5. Bất biến: `final` không đồng nghĩa bất biến sâu

Record tự sinh trường `private final` cho mỗi component. Ví dụ:

```java
record Team(List<String> members) {}
```

Trường `members` **không thể trỏ sang một danh sách khác sau khi khởi tạo**, nhưng nếu nó trỏ tới một `ArrayList` được chia sẻ, bên ngoài vẫn có thể thêm/xóa phần tử:

```java
// Minh họa lỗi thiết kế: record giữ nguyên tham chiếu đầu vào.
List<String> external = new ArrayList<>(List.of("An"));
Team team = new Team(external);
external.add("Bình");
System.out.println(team.members());  // [An, Bình]
```

Ở đây có **hai loại bất biến** cần tách biệt:

- **Bất biến nông (shallow immutability):** tham chiếu trong component field là `final`, không bị gán lại.
- **Bất biến sâu (deep immutability):** toàn bộ trạng thái có thể quan sát thông qua component, bao gồm các phần tử bên trong cấu trúc dữ liệu, không thể bị thay đổi từ bên ngoài.

Record **chỉ bảo đảm phần thứ nhất qua các component field `final`**. Phần thứ hai phụ thuộc vào kiểu component và cách phòng vệ.

### 5.1. Defensive copy ở đầu vào

Cách thông dụng với `List<String>`:

```java
public record SafeTeam(List<String> members) {
    public SafeTeam {
        members = List.copyOf(
                java.util.Objects.requireNonNull(members, "members"));
    }
}
```

`List.copyOf` trả danh sách **không thể thêm/xóa/thay phần tử**. Bên gọi giữ `ArrayList` ban đầu thì sửa nó cũng không làm danh sách record thay đổi. `List.copyOf` có thể dùng lại một danh sách sẵn có nếu đã không thể sửa; hợp đồng cần dựa vào **tính không sửa được**, không phụ thuộc danh tính đối tượng danh sách trả về.

Với `List<String>`, `String` tự nó bất biến, nên tổ hợp này đủ phù hợp để giữ nội dung danh sách ổn định. Nhưng với `List<MutablePerson>`, sao chép danh sách **không sao chép sâu các `MutablePerson`**. Nếu phần tử có setter, người giữ tham chiếu đến phần tử vẫn có thể sửa thuộc tính của nó; khi cần bất biến sâu, ưu tiên kiểu phần tử bất biến hoặc bản sao thích hợp cho từng phần tử.

**Lưu ý về `null`:** `List.copyOf` cấm danh sách đầu vào `null` và cấm phần tử `null`. Nếu domain cho phép giá trị thiếu, cần thiết kế mô hình khác thay vì mặc định chấp nhận `null`.

### 5.2. Đặc biệt cẩn thận với mảng và `Date` mutable

Chỉ copy ở constructor là **chưa đủ** nếu accessor trả lại tham chiếu tới mảng mutable. Ví dụ đúng ở mức ngăn sửa byte bên trong:

```java
public record BytePayload(byte[] data) {
    public BytePayload {
        data = java.util.Objects.requireNonNull(data, "data").clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }
}
```

Mẫu trên tạo bản sao **khi nhận** và **khi trả** mảng, bảo vệ trạng thái byte nội bộ của record. **Tuy nhiên**, `equals/hashCode` mà compiler tự sinh cho component kiểu mảng không so sánh nội dung mảng từng phần tử; chúng theo ngữ nghĩa đối tượng mảng. Nếu yêu cầu so sánh theo *nội dung*, cần tự định nghĩa `equals`/`hashCode` nhất quán (chẳng hạn dùng `Arrays.equals` và `Arrays.hashCode`), hoặc chọn kiểu component đã có ngữ nghĩa value phù hợp. Không nhầm “đã copy mảng” với “đã có value equality đúng yêu cầu”.

Với kiểu thời gian như `LocalDate` trong ví dụ chính, giá trị được mô hình hóa là bất biến nên không cần defensive copy. Ngược lại, `java.util.Date` có trạng thái có thể sửa và cần xử lý sao chép hoặc đổi sang kiểu thời gian hiện đại như `LocalDate`/`Instant` theo nghiệp vụ.

### 5.3. Không dùng setter hay thay đổi component của chính record

Record không tự sinh setter cho component. Các trường component là `final`, nên không thể gán `stay.guestNames = ...` hoặc `this.guestNames = ...` sau khi xây dựng.

Khi cần “cập nhật”, thường **tạo đối tượng mới**:

```java
// Đoạn minh họa đặt trong phương thức có biến original kiểu Stay.
Stay updated = original.withGuestNames(List.of("An", "Chi"));
```

Không nên biến record thành đối tượng chứa trạng thái ẩn mutable chỉ để mô phỏng setter. Nếu thực sự cần một entity có vòng đời thay đổi liên tục, class bình thường và cơ chế quản lý state riêng có thể phù hợp hơn.

## 6. Canonical constructor dạng đầy đủ và constructor bổ sung

### 6.1. Dạng đầy đủ tự gán các component field

Có thể viết constructor chuẩn với đầy đủ danh sách tham số (đây là **tệp độc lập `Range.java`**, thay thế việc dùng compact constructor cho cùng record):

```java
public record Range(int min, int max) {
    public Range(int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min phải <= max");
        }
        this.min = min;
        this.max = max;
    }
}
```

**Khác compact constructor:** dạng đầy đủ cho phép và đòi hỏi bạn tự bảo đảm các component field được gán chính xác; không có bước tự gán mặc định giống compact constructor. Không thể viết **đồng thời** cả canonical constructor dạng đầy đủ và compact canonical constructor cho cùng một record.

### 6.2. Constructor bổ sung phải đi qua canonical constructor

Giả sử muốn cho phép tạo `Stay` với một danh sách khách mặc định. Có thể **bổ sung bên trong định nghĩa `Stay` ở ví dụ chính**:

```java
public Stay(String bookingId, LocalDate checkIn, LocalDate checkOut) {
    this(bookingId, checkIn, checkOut, List.of("Khách"));
}
```

Đây chỉ là đoạn constructor **minh họa để thêm vào record `Stay`**, không phải chương trình độc lập. Nó **ủy quyền tới canonical constructor** có bốn tham số, nên mọi dữ liệu cuối cùng vẫn phải qua kiểm tra ngày, mã và danh sách khách. Trên Java hiện đại, constructor không chuẩn của record phải gọi constructor khác của cùng record qua `this(...)` để bảo đảm đường khởi tạo hợp lệ.

Không đặt các đường khởi tạo “bỏ qua validation”. Khi cần factory, factory nên tạo record qua constructor đã bảo vệ invariant.

## 7. Ngoại lệ, chuẩn hóa và hợp đồng của record

### 7.1. Chuẩn hóa trước khi lưu, nhưng thống nhất với bình đẳng giá trị

Compact constructor có thể chuẩn hóa tham số:

```java
public record EmailAddress(String value) {
    public EmailAddress {
        value = java.util.Objects.requireNonNull(value, "value").strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("email rỗng");
        }
    }
}
```

Ở đây chỉ chuẩn hóa khoảng trắng hai đầu, **chưa kiểm tra cú pháp email**; nếu domain cần địa chỉ email hợp lệ, phải xác định rõ rule thay vì coi `strip()` là đủ.

Hai `EmailAddress` tạo từ `" x@y.example "` và `"x@y.example"` có cùng giá trị component sau chuẩn hóa, nên `equals` tự sinh trả `true`. Cần quyết định chuẩn hóa ngay khi khởi tạo để trạng thái bên trong không thay đổi về sau và `hashCode` giữ ổn định.

### 7.2. Accessor tùy chỉnh có thể phá hợp đồng thiết kế

Có thể tự viết accessor của record, nhưng cần giữ ý nghĩa của component và tránh trả về trực tiếp tham chiếu mutable. Một record bảo toàn dữ liệu tốt thường cho phép “copy từ các accessor rồi xây lại” cho ra đối tượng tương đương:

```java
// Minh họa: các giá trị accessor bảo toàn component đã chuẩn hóa.
Stay copy = new Stay(
        original.bookingId(),
        original.checkIn(),
        original.checkOut(),
        original.guestNames());
System.out.println(original.equals(copy)); // true
```

Với ví dụ chính, điều này đúng vì các component được chuẩn hóa ổn định, `LocalDate`/`String` là kiểu bất biến và `List<String>` có ngữ nghĩa so sánh theo nội dung. Nếu tự viết accessor trả giá trị không phản ánh component hoặc sửa state bên trong, việc sử dụng record sẽ khó dự đoán.

### 7.3. Hệ quả khi dùng làm key của `HashMap` hoặc `HashSet`

Các phương thức `equals`/`hashCode` tự sinh dựa trên component. Nếu component chứa object mutable rồi bị đổi sau khi record được đưa vào `HashMap` làm key, giá trị hash/so sánh có thể thay đổi và thao tác tra cứu gặp lỗi khó hiểu. Vì thế, **defensive copy và kiểu component bất biến** đặc biệt quan trọng khi record biểu diễn khóa hoặc giá trị dùng trong cache.

## 8. Lỗi phổ biến và cách xử lý

| Lỗi hoặc hiểu nhầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| “`record` tự kiểm tra các ràng buộc nghiệp vụ” | Tạo được khoảng ngày sai, chuỗi rỗng, danh sách không hợp lệ | Kiểm tra trong canonical/compact constructor |
| “Khi throw, vẫn có record hợp lệ để gán vào biến” | Biểu thức `new` bị ngắt; không trả về đối tượng tạo thành công | Bắt/để lan truyền exception ở nơi phù hợp; không dùng kết quả khi khởi tạo thất bại |
| “Bắt mọi exception rồi tiếp tục constructor là an toàn” | Invariant bị bỏ qua hoặc dữ liệu sai được che giấu | Sửa dữ liệu hợp lệ hoặc cho exception lan truyền |
| “`final List` nghĩa là mọi phần tử bất biến” | Bên ngoài vẫn sửa được collection/đối tượng thành phần | Dùng `List.copyOf`, phần tử bất biến hoặc defensive copy sâu |
| “Compact constructor phải gán `this.component`” | Lỗi biên dịch | Chuẩn hóa **tham số**, để compiler tự gán field |
| “Copy input list là đủ với mọi loại component” | Mảng/object mutable vẫn có thể lộ qua accessor | Kiểm soát cả lúc nhận và lúc trả; chọn kiểu phù hợp |
| “`List.copyOf` chấp nhận null” | Ném `NullPointerException` | Xác định chính sách null rõ ràng trước khi copy |
| “Constructor khác có thể bỏ qua canonical” | Vi phạm quy tắc của record và thiết kế invariant | Ủy quyền qua `this(...)` tới đường khởi tạo hợp lệ |
| “Record có `final` sẽ tự hoàn tác mọi side effect nếu constructor lỗi” | Database, file, dịch vụ ngoài có thể đã đổi | Tránh side effect trong constructor; đặt giao dịch ở service |
| “Record luôn phù hợp entity mutable” | Không có setter/instance field tùy ý theo mô hình class thường | Dùng record cho dữ liệu theo component; dùng class khi cần vòng đời mutable |

**Checklist khi thiết kế một record mới:**

1. Viết ra mọi **invariant**: điều kiện null, miền giá trị, quan hệ giữa nhiều component, điều kiện về collection.
2. Đặt validation tại **canonical constructor** (compact nếu chỉ cần kiểm tra/chuẩn hóa).
3. Chọn exception có ý nghĩa, thông điệp đủ rõ nhưng không làm lộ dữ liệu nhạy cảm.
4. Chuẩn hóa **tham số** trước khi lưu; không ghi `this.component` trong compact constructor.
5. Kiểm tra component mutable: defensive copy ở đầu vào, ở accessor nếu cần, và bất biến của phần tử.
6. Bảo đảm constructor bổ sung/factory không bỏ qua quy tắc.
7. Kiểm thử **cả đầu vào hợp lệ lẫn sai** (null, rỗng, quan hệ chéo, mutable list, phần tử null), cùng việc đối tượng đã tạo không đổi sau thao tác bên ngoài.
8. Nếu muốn cập nhật, tạo **record mới**, giữ validation; tránh mutation ngầm làm thay đổi `equals/hashCode`.
9. Tránh tác dụng phụ trong constructor và xử lý giao dịch tại tầng nghiệp vụ thích hợp.

## 9. Tài liệu chính thức, hiện còn áp dụng

- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): records được chuẩn hóa từ Java 16, compact/canonical constructors và bất biến.
- [Java Language Specification — Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10.4): quy tắc ngôn ngữ về constructor, gán component và phạm vi hợp lệ.
- [Dev.java — Using Records to Model Immutable Data](https://dev.java/learn/using-record-to-model-immutable-data/): validation, defensive copy, compact constructor.
- [Java SE API — List.copyOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): danh sách không thể sửa và cách xử lý `null`.

**Ghi nhớ:** *Record chỉ có các component field `final`; invariant và bất biến quan sát được phải được thiết kế và bảo vệ.* Constructor kiểm tra/chuẩn hóa; đầu vào sai thì ném ngoại lệ; dữ liệu mutable thì sao chép phòng vệ; cập nhật có chủ ý thì xây record mới qua cùng cơ chế validation.
