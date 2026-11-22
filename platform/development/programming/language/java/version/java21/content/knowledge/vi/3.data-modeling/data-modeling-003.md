# Thiết kế record có validation và giữ invariant của dữ liệu

## 1. Record dùng để biểu diễn dữ liệu có giá trị rõ ràng

Trong Java 21, `record` là một dạng khai báo kiểu dành cho những đối tượng mà trạng thái dữ liệu được xác định bởi một tập component cố định. Record phù hợp với value object, kết quả truy vấn, thông điệp trao đổi và DTO có cấu trúc rõ ràng.

Khi khai báo một record, compiler cung cấp các thành phần mặc định dựa trên danh sách component nếu bạn không tự khai báo: field `private final`, accessor cùng tên component, canonical constructor, và các triển khai `equals`, `hashCode`, `toString`. Record là `final`, kế thừa trực tiếp `java.lang.Record` và không thể khai báo thêm instance field ngoài các component. Bạn vẫn có thể khai báo method, constructor bổ sung, static field, static method và triển khai interface.

Ví dụ đơn giản:

```java
public record CustomerId(String value) {
}
```

Record trên có component `value`, accessor `value()` và canonical constructor nhận một `String`. Tuy nhiên, khai báo record đơn thuần chưa đảm bảo dữ liệu hợp lệ. `new CustomerId(null)` vẫn có thể được gọi nếu constructor không kiểm tra. Để giữ invariant, mọi đường tạo đối tượng cần đi qua constructor có validation phù hợp.

Một invariant là điều kiện phải luôn đúng đối với mọi instance hợp lệ. Ví dụ: mã khách hàng không rỗng, số lượng đặt hàng lớn hơn 0, ngày kết thúc không trước ngày bắt đầu, hoặc danh sách nhãn không thể bị thay đổi từ bên ngoài.

## 2. Dùng compact constructor để kiểm tra và chuẩn hóa dữ liệu

Với record, cách thường dùng để kiểm tra dữ liệu là khai báo **compact canonical constructor**. Cú pháp này không cần lặp lại danh sách tham số và không cần tự gán từng field:

```java
import java.util.Objects;

public record CustomerId(String value) {
    public CustomerId {
        value = Objects.requireNonNull(value, "value").strip();

        if (value.isEmpty()) {
            throw new IllegalArgumentException("Customer ID must not be blank");
        }
    }
}
```

Trong compact constructor, các tên component được dùng như tham số constructor. Compiler tự gán giá trị tham số vào field tương ứng sau khi phần thân constructor hoàn tất. Vì vậy, có thể gán lại tham số để chuẩn hóa dữ liệu, nhưng không viết `this.value = value` trong compact constructor.

Đoạn mã trên thực hiện hai loại kiểm tra:

- `Objects.requireNonNull` từ chối `null` và nêu rõ component vi phạm.
- `strip()` loại bỏ khoảng trắng ở hai đầu; sau đó kiểm tra chuỗi rỗng và ném `IllegalArgumentException` nếu dữ liệu không hợp lệ.

Chuẩn hóa trước khi kiểm tra các điều kiện phụ thuộc vào giá trị đã chuẩn hóa. Ví dụ, nếu mã định danh không phân biệt chữ hoa chữ thường, có thể chuẩn hóa bằng `toUpperCase(Locale.ROOT)` để kết quả không phụ thuộc locale mặc định của máy chạy.

## 3. Ví dụ record có nhiều invariant

Một dòng hàng trong đơn hàng có thể cần giữ các quy tắc: mã hàng không được để trống, số lượng phải dương, đơn giá không âm và danh sách nhãn phải ổn định sau khi tạo đối tượng.

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public record OrderLine(
        String sku,
        int quantity,
        BigDecimal unitPrice,
        List<String> tags
) {
    public OrderLine {
        sku = Objects.requireNonNull(sku, "sku")
                .strip()
                .toUpperCase(Locale.ROOT);

        if (sku.isEmpty()) {
            throw new IllegalArgumentException("sku must not be blank");
        }

        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be greater than zero");
        }

        unitPrice = Objects.requireNonNull(unitPrice, "unitPrice");
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("unitPrice must not be negative");
        }

        tags = List.copyOf(Objects.requireNonNull(tags, "tags"));
        if (tags.stream().anyMatch(String::isBlank)) {
            throw new IllegalArgumentException("tags must not contain blank values");
        }
    }
}
```

Mọi lời gọi canonical constructor đều chạy qua validation này, kể cả khi code gọi trực tiếp `new OrderLine(...)`. Sau khi constructor kết thúc, instance có mã hàng đã chuẩn hóa, số lượng hợp lệ, đơn giá không âm và danh sách nhãn không thể bị sửa đổi qua accessor.

Ví dụ sử dụng:

```java
var line = new OrderLine(
        " ab-120 ",
        2,
        new BigDecimal("19.90"),
        List.of("sale", "gift")
);

System.out.println(line.sku());       // AB-120
System.out.println(line.quantity());  // 2
```

Nếu truyền số lượng bằng `0`, đơn giá âm, danh sách `null` hoặc nhãn rỗng, constructor từ chối tạo instance. `List.copyOf` cũng từ chối phần tử `null` và trả về một list không thể sửa đổi.

## 4. Giữ invariant liên quan đến nhiều component

Không phải quy tắc nào cũng kiểm tra được trên từng field riêng lẻ. Một số invariant phụ thuộc vào quan hệ giữa nhiều component. Ví dụ, khoảng ngày phải có ngày kết thúc bằng hoặc sau ngày bắt đầu:

```java
import java.time.LocalDate;
import java.util.Objects;

public record DateRange(LocalDate start, LocalDate end) {
    public DateRange {
        start = Objects.requireNonNull(start, "start");
        end = Objects.requireNonNull(end, "end");

        if (end.isBefore(start)) {
            throw new IllegalArgumentException("end must not be before start");
        }
    }
}
```

Khi kiểm tra invariant liên trường, hãy kiểm tra null trước khi gọi method trên component. Nếu cho phép hai đầu mút bằng nhau, ví dụ trên chấp nhận khoảng ngày chỉ có một ngày. Nếu nghiệp vụ yêu cầu ngày kết thúc phải sau ngày bắt đầu, đổi điều kiện thành `!end.isAfter(start)`.

Các invariant thường gặp khác:

- `minimum <= maximum` đối với một khoảng giá trị.
- `currency` và `amount` phải cùng tuân theo chính sách tiền tệ đã chọn.
- Trạng thái và thời điểm hoàn tất phải nhất quán, chẳng hạn trạng thái hoàn tất cần có `completedAt`.
- Một tập component phải cùng thuộc một loại hoặc một phiên bản dữ liệu.

Hãy mô tả rõ chính sách cho từng trường hợp biên. Tránh để điều kiện nghiệp vụ chỉ tồn tại trong comment hoặc ở một màn hình nhập liệu, vì code khác vẫn có thể gọi constructor trực tiếp.

## 5. Defensive copy để ngăn thay đổi từ bên ngoài

Field của record là `final`, nhưng điều đó chỉ ngăn gán lại tham chiếu. Nó không làm cho đối tượng được tham chiếu trở nên bất biến. Ví dụ, nếu một record giữ `List<String>`, một list có thể thay đổi vẫn có thể bị sửa thông qua tham chiếu khác nếu record lưu trực tiếp list ban đầu.

Hãy tạo bản sao không thể sửa đổi khi nhận collection:

```java
import java.util.List;
import java.util.Objects;

public record SearchResult(List<String> items) {
    public SearchResult {
        items = List.copyOf(Objects.requireNonNull(items, "items"));
    }
}
```

Với collection chuẩn, các phương thức `List.copyOf`, `Set.copyOf` và `Map.copyOf` tạo collection không thể sửa đổi. Chúng cũng từ chối collection đầu vào `null`; các phần tử `null` (hoặc key/value `null` với map) không được chấp nhận. Chọn chính sách này khi dữ liệu của bạn không cần chứa `null`.

Đây là **bản sao nông (shallow copy)**. Nếu collection chứa object có thể thay đổi, collection mới vẫn giữ tham chiếu đến các object đó. Để đảm bảo trạng thái không bị thay đổi gián tiếp, hãy dùng phần tử bất biến hoặc tạo bản sao phù hợp cho từng phần tử.

Với mảng, cần cẩn thận hơn vì accessor được sinh tự động trả về chính tham chiếu mảng bên trong. Nếu bắt buộc phải dùng mảng, hãy sao chép cả lúc nhận và lúc trả về:

```java
import java.util.Objects;

public record Digest(byte[] bytes) {
    public Digest {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
```

Ví dụ này bảo vệ nội dung mảng khỏi bị thay đổi qua tham chiếu đầu vào hoặc accessor. Tuy nhiên, `equals` và `hashCode` được sinh cho record vẫn áp dụng ngữ nghĩa của component; với mảng, điều đó không tạo ra so sánh nội dung như `Arrays.equals`. Nếu cần value equality theo nội dung mảng, phải tự định nghĩa `equals` và `hashCode` tương ứng hoặc chọn kiểu dữ liệu khác phù hợp hơn.

## 6. Chọn nơi đặt validation

Validation nên được đặt tại nơi có thể bảo vệ invariant một cách nhất quán:

| Loại quy tắc | Nơi phù hợp | Ví dụ |
|---|---|---|
| Không null, không rỗng, giới hạn số học | Compact constructor | `quantity > 0` |
| Quan hệ giữa các component | Compact constructor | `end` không trước `start` |
| Chuẩn hóa biểu diễn dữ liệu | Compact constructor hoặc static factory | `strip()`, chuẩn hóa mã |
| Phân tích đầu vào bên ngoài có nhiều định dạng | Static factory hoặc lớp mapper | Chuyển chuỗi ngày thành `LocalDate` |
| Kiểm tra phụ thuộc cơ sở dữ liệu, quyền truy cập hoặc trạng thái hệ thống | Service/domain logic phù hợp | Mã khách hàng có tồn tại hay người dùng có quyền đặt hàng |

Constructor nên thực hiện kiểm tra nhanh, xác định và không có side effect. Không gọi database, gửi request mạng, ghi file hoặc phụ thuộc vào trạng thái thay đổi bên ngoài trong constructor. Những điều kiện đó có thể thay đổi theo thời gian và khiến việc tạo một value object trở nên khó dự đoán.

Nếu đầu vào cần parsing hoặc quy trình tạo phức tạp, có thể cung cấp static factory:

```java
import java.util.Objects;

public record CustomerId(String value) {
    public CustomerId {
        value = Objects.requireNonNull(value, "value").strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("value must not be blank");
        }
    }

    public static CustomerId from(String rawValue) {
        return new CustomerId(rawValue);
    }
}
```

Static factory giúp đặt tên cho ý định tạo đối tượng hoặc gom parsing, nhưng vẫn nên để canonical constructor bảo vệ invariant. Nếu chỉ kiểm tra trong factory, caller vẫn có thể bỏ qua factory và gọi constructor trực tiếp.

## 7. Lựa chọn exception và tránh các cách kiểm tra không phù hợp

- Dùng `Objects.requireNonNull(value, "value")` khi component bắt buộc có giá trị. Nó ném `NullPointerException` với thông tin component.
- Dùng `IllegalArgumentException` khi giá trị có mặt nhưng không thỏa điều kiện, chẳng hạn số lượng âm hoặc khoảng ngày không hợp lệ.
- Không dùng `assert` để bảo vệ dữ liệu đầu vào. Assertion có thể bị tắt khi chạy JVM, vì vậy không phù hợp làm cơ chế validation bắt buộc.
- Không chỉ validate trong setter, controller hoặc giao diện nhập liệu. Record không có setter mặc định và mọi constructor công khai phải giữ được invariant.
- Tránh validation có side effect hoặc kết quả phụ thuộc thời điểm, vì nó làm cho việc tạo cùng một giá trị trở nên không nhất quán.

Nếu dự án dùng Jakarta Bean Validation hoặc framework tương tự, annotation constraint có thể bổ sung metadata cho tầng tích hợp. Tuy nhiên, annotation chỉ được thực thi khi có validator được gọi. Với invariant cốt lõi của record, constructor vẫn là điểm bảo vệ trực tiếp và độc lập với việc framework có được cấu hình hay không.

## 8. Hiểu đúng value equality của record

Compiler sinh `equals` và `hashCode` dựa trên các component. Do đó, danh sách component chính là một phần của định nghĩa giá trị và hợp đồng API của record.

Ví dụ, hai `CustomerId` có cùng chuỗi sau chuẩn hóa sẽ có giá trị bằng nhau:

```java
var first = new CustomerId(" cust-01 ");
var second = new CustomerId("CUST-01");

System.out.println(first.equals(second)); // true
```

Khi thiết kế component, hãy xem xét:

- Mỗi component có thực sự tham gia định nghĩa giá trị của object không?
- Giá trị có được chuẩn hóa trước khi lưu để equality nhất quán không?
- Kiểu component có `equals` phù hợp với ý nghĩa nghiệp vụ không?
- `toString()` tự sinh có vô tình hiển thị dữ liệu nhạy cảm không?

Ví dụ, `BigDecimal.equals` phân biệt scale: `new BigDecimal("1.0")` không bằng `new BigDecimal("1.00")`, dù hai giá trị so sánh số học bằng nhau qua `compareTo`. Nếu scale không thuộc ý nghĩa nghiệp vụ, hãy chuẩn hóa theo chính sách rõ ràng trước khi lưu. Không nên tự động đặt scale hoặc làm tròn nếu nghiệp vụ chưa quy định cách xử lý.

Mọi component cũng xuất hiện trong accessor và thường được đưa vào `toString()` sinh tự động. Không đưa mật khẩu, token bí mật hoặc dữ liệu nhạy cảm vào record công khai mà không cân nhắc cách hiển thị và logging; nếu cần, hãy kiểm soát `toString()` hoặc thiết kế kiểu lưu trữ phù hợp hơn.

## 9. Khi nào nên và không nên dùng record?

Record phù hợp khi:

- Đối tượng chủ yếu biểu diễn một tập giá trị cố định.
- Các component là dữ liệu công khai và cùng xác định equality.
- Có thể bảo vệ invariant tại thời điểm tạo.
- Không cần thay đổi trạng thái sau khi tạo instance.

Hãy cân nhắc một class thông thường khi:

- Đối tượng có vòng đời mutable với nhiều thao tác thay đổi trạng thái.
- Danh tính đối tượng độc lập với toàn bộ giá trị component.
- Cần kế thừa từ một class khác hoặc cần thiết kế hệ phân cấp class.
- Cần instance field bổ sung không phải component, hoặc cần che giấu cấu trúc dữ liệu nội bộ khỏi API công khai.
- Các giá trị được giữ bên trong không thể được bảo vệ khỏi thay đổi ngoài ý muốn.

Không nên thêm một component chỉ để chứa cache hoặc trạng thái kỹ thuật nếu nó không thuộc giá trị của record. Vì component tham gia constructor, accessor, equality, hash code và chuỗi biểu diễn, thêm hoặc đổi component là thay đổi hợp đồng mà caller có thể phụ thuộc vào.

## 10. Checklist thiết kế record an toàn

Trước khi đưa record vào sử dụng, hãy kiểm tra:

1. Danh sách component có thể hiện đúng dữ liệu cấu thành giá trị của object không?
2. Đã xác định rõ component nào bắt buộc khác `null` chưa?
3. Đã kiểm tra miền giá trị và invariant liên trường chưa?
4. Dữ liệu có cần chuẩn hóa trước khi gán vào component không?
5. Collection hoặc mảng đầu vào đã được defensive copy chưa?
6. Các object nằm bên trong collection có bất biến hoặc được bảo vệ phù hợp không?
7. `equals`, `hashCode` và `toString` sinh tự động có phù hợp với ý nghĩa dữ liệu và yêu cầu bảo mật không?
8. Validation có thuần túy, nhanh và không phụ thuộc dịch vụ bên ngoài không?
9. Mọi constructor có bảo đảm cùng một invariant không?

## 11. Tài liệu tham khảo chính thức

- [Java Language Specification, Java SE 21 — Record Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10): quy tắc khai báo record, component và constructor.
- [Java SE 21 API — `java.lang.Record`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Record.html): lớp nền của record và hợp đồng về các method được sinh.
- [Java SE 21 API — `java.util.Objects`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html): các tiện ích kiểm tra null và thao tác object.
- [Java SE 21 API — `List.copyOf`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): tạo list không thể sửa đổi từ collection đầu vào.

Điểm cốt lõi là coi canonical constructor như ranh giới tạo dữ liệu hợp lệ. Kết hợp validation, chuẩn hóa và defensive copy tại đó giúp mọi instance record tuân thủ invariant ngay từ khi được tạo, miễn là các component bên trong cũng được thiết kế để không làm thay đổi giá trị ngoài dự kiến.
