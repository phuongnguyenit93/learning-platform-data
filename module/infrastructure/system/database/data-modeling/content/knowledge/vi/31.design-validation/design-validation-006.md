# Kiểm thử equals, hashCode và tính bất biến của mô hình Java

## 1. Từ mô hình dữ liệu đến hợp đồng của đối tượng Java

Module **DATABASE_DATA_MODELING** rèn khả năng chuyển yêu cầu nghiệp vụ thành mô hình có thực thể, quan hệ, khóa, ràng buộc, chuẩn hóa, chỉ mục và lược đồ vật lý; so sánh các cách lưu dữ liệu quan hệ, document, đồ thị và phân tích. Trong chương **Kiểm chứng thiết kế**, không chỉ DDL và SQL cần được xác minh: các đối tượng Java còn phải thể hiện đúng **danh tính, bình đẳng và bất biến** của mô hình.

Xét một hệ thống bán lẻ đa tenant, nơi SKU được nhận diện bởi bộ ba:

~~~text
tenantCode  = VN-01
catalogCode = MAIN
skuCode     = P0012
~~~

Request HTTP tạo một đối tượng Sku. Worker đọc database tạo một Sku khác có ba giá trị tương đương. Đây là **hai instance** nhưng cùng một **khóa nghiệp vụ**.

Nếu ứng dụng dùng HashSet để chống trùng hoặc HashMap để tra hàng tồn, kết quả phụ thuộc vào **equals/hashCode**. Nếu đối tượng bị sửa sau khi được dùng làm khóa Map, lookup có thể sai. Nếu ProductVersion thuộc SCD2 bị coi là ProductIdentity, hai phiên bản cùng mã sản phẩm có thể bị gộp và gây sai lịch sử.

Bài này kiểm chứng ba lớp:

1. **Equality:** khi nào hai đối tượng được coi là cùng giá trị hoặc cùng thực thể?
2. **Hashing:** đối tượng bằng nhau có thể được tra cứu nhất quán trong cấu trúc hash không?
3. **Immutability và invariants:** trạng thái nào được phép thay đổi, trạng thái nào phải cố định, và điều kiện nào luôn phải đúng?

**Mục tiêu học tập:** thiết kế value object và entity identity; viết equals/hashCode tuân hợp đồng Java; phát hiện lỗi với HashSet/HashMap, record, mảng, collection, BigDecimal, temporal values, inheritance và JPA; xây test JUnit 5, property-based và kiểm thử tích hợp để khớp với khóa/UNIQUE/FK của database.

## 2. Chọn quy tắc bình đẳng theo grain và danh tính

Không phải mọi đối tượng có thuộc tính bằng nhau đều là cùng một thực thể.

| Loại mô hình | Ví dụ | Bình đẳng cần định nghĩa |
|---|---|---|
| **Value object** | Sku, Money, EmailAddress, ValidInterval | Cùng các giá trị cấu thành đã chuẩn hóa |
| **Entity** | Customer, SalesOrder, Product | Cùng danh tính ổn định, không phụ thuộc mọi thuộc tính mutable |
| **Phiên bản entity** | ProductVersion, PriceVersion | Cùng version ID, không chỉ cùng mã entity gốc |
| **Event** | OrderCreated | Cùng event ID, không chỉ cùng payload |
| **Request** | CreateOrderRequest | Cùng request ID trong phạm vi tenant/client |
| **DTO/snapshot** | OrderSummary | Có thể bằng theo các trường snapshot nếu contract nêu vậy |
| **Fact phân tích** | Một dòng bán | Cùng source line identity, không chỉ cùng số tiền |
| **Aggregate** | Order gồm nhiều dòng | Cùng aggregate ID, không so đệ quy toàn bộ quan hệ |

Ví dụ hai đơn O100 và O101 có thể cùng khách, sản phẩm, số lượng và số tiền. Chúng vẫn là **hai đơn khác nhau**. Nếu equals so theo các trường nội dung và trả true, HashSet có thể loại bỏ một đơn hợp lệ.

Ngược lại, hai Money có cùng số lượng tiền và cùng currency có thể là cùng **giá trị**, bất kể là hai instance.

### 2.1. Trước khi code, viết invariant một câu

~~~text
Hai Sku bằng nhau nếu và chỉ nếu cùng tenant,
cùng catalog và cùng code theo quy tắc nguồn.

Hai SalesOrder bằng nhau nếu và chỉ nếu có cùng
danh tính order ổn định trong namespace thích hợp.

Hai ProductVersion bằng nhau nếu và chỉ nếu
có cùng định danh phiên bản, không chỉ cùng productId.
~~~

Một invariant đã được viết rõ giúp chọn đúng field. Không tự so status, description, updatedAt hoặc cachedAmount chỉ vì chúng xuất hiện trên object.

### 2.2. Grain khác thì equality khác

~~~text
ProductIdentity:
  grain = một sản phẩm logic
  key = (tenantId, sourceSystem, productCode)

ProductVersion:
  grain = một phiên bản mô tả có khoảng hiệu lực
  key = productVersionId

SalesLine:
  grain = một dòng bán đã ghi nhận
  key = (tenantId, salesSource, sourceLineId)
~~~

Hai phiên bản sản phẩm có thể cùng productCode nhưng khác versionId. Một Map keyed theo ProductIdentity không thể giữ đồng thời hai giá trị khác nhau của mọi phiên bản nếu chỉ một entry cho một key.

## 3. Hợp đồng Object.equals

Trong Java, equals của một đối tượng không null phải thỏa:

1. **Reflexive (phản xạ):** x.equals(x) là true.
2. **Symmetric (đối xứng):** x.equals(y) và y.equals(x) có cùng kết quả.
3. **Transitive (bắc cầu):** x bằng y, y bằng z thì x bằng z.
4. **Consistent (nhất quán):** nếu dữ liệu dùng để so sánh không đổi, các lần gọi trả cùng kết quả.
5. **Non-null:** x.equals(null) là false.

Các điều kiện này là hợp đồng của Java Object, không phải khuyến nghị trình bày. Map, Set và framework dựa vào chúng.

### 3.1. == không phải equals cho reference

~~~java
Sku a = new Sku("VN-01", "MAIN", "P0012");
Sku b = new Sku("VN-01", "MAIN", "P0012");
Sku alias = a;

System.out.println(a == alias);  // true: cùng instance
System.out.println(a == b);      // false: instance khác
System.out.println(a.equals(b)); // true: cùng giá trị Sku
~~~

Dấu == trên reference so **danh tính instance**, không phải business key. Trên primitive như int, == so giá trị primitive.

### 3.2. Phép so xấp xỉ không phù hợp với equals

Một phép so gần nhau:

~~~java
boolean approximatelyEqual(double a, double b) {
    return Math.abs(a - b) < 0.1;
}
~~~

không có tính bắc cầu:

~~~text
a = 0.00, b = 0.09, c = 0.18

a ~ b: true
b ~ c: true
a ~ c: false
~~~

Không dùng tolerance làm equality của một value object. Với dữ liệu đo đạc cần độ sai số, hãy tạo **isApproximatelyEqual(other, tolerance)** hoặc chuẩn hóa phép đo theo quy tắc nghiệp vụ trước khi tạo key.

## 4. Hợp đồng hashCode: bằng nhau thì phải cùng hash

Hợp đồng cơ bản:

> Nếu x.equals(y) là true thì x.hashCode() phải bằng y.hashCode().

Chiều ngược **không bắt buộc**: hai đối tượng khác nhau có thể có cùng hash. HashMap/HashSet chịu trách nhiệm xử lý va chạm và so equality khi cần.

~~~text
equals(x, y) == true  => hash(x) == hash(y)
hash(x) == hash(y)    không suy ra equals(x, y) == true
~~~

### 4.1. Hash collision không tự là lỗi hợp đồng

~~~java
@Override
public int hashCode() {
    return 1;
}
~~~

Nếu equals đúng, hash constant không vi phạm điều kiện equal-implies-same-hash, nhưng **phân phối hash rất kém** khi số phần tử tăng. Mục tiêu là hash nhất quán và phân phối hữu ích, không phải unique tuyệt đối.

### 4.2. hashCode không phải định danh phân tán

Không được dùng hashCode làm:

- Business key/PRIMARY KEY.
- ID duy nhất toàn hệ thống.
- Cryptographic digest/chữ ký hay password hash.
- Khóa phân vùng ổn định nhiều phiên bản dịch vụ nếu chưa có contract chuyên biệt.
- Thước đo thứ tự tạo hoặc commit của entity.

Đó chỉ là một mã phục vụ nhiều cấu trúc Java. Nếu yêu cầu UUID, khóa ghép có namespace hoặc checksum, hãy thiết kế công cụ tương ứng.

## 5. Record Sku: value object bất biến cơ bản

Ví dụ Java 17:

~~~java
import java.util.Objects;

public record Sku(
        String tenantCode,
        String catalogCode,
        String skuCode
) {
    public Sku {
        tenantCode = requireNonBlank("tenantCode", tenantCode);
        catalogCode = requireNonBlank("catalogCode", catalogCode);
        skuCode = requireNonBlank("skuCode", skuCode);
    }

    private static String requireNonBlank(String field, String value) {
        Objects.requireNonNull(value, field);
        if (value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return value;
    }
}
~~~

Record tự sinh **equals, hashCode và toString** từ các component. Các component đều String bất biến; constructor ngăn giá trị null/rỗng chỉ chứa whitespace. Vì không có setter và String không sửa được, nội dung khóa không thay đổi sau khi tạo.

~~~java
Sku a = new Sku("VN-01", "MAIN", "P0012");
Sku b = new Sku("VN-01", "MAIN", "P0012");
Sku c = new Sku("VN-02", "MAIN", "P0012");

System.out.println(a.equals(b));                // true
System.out.println(a.hashCode() == b.hashCode()); // true
System.out.println(a.equals(c));                // false
~~~

**Tenant phải nằm trong equality** nếu SKU chỉ unique trong phạm vi tenant. Nếu mã nguồn thực tế case-insensitive hay cần chuẩn hóa, phải thay constructor và test theo quy tắc nguồn, không tùy tiện áp lên tất cả hệ thống.

### 5.1. Record không dành cho mọi entity

Record phù hợp **value carrier** có thành phần rõ. Một entity có ID, vòng đời trạng thái, lazy relations và ORM proxy có thể phù hợp với class thông thường hơn. Mục tiêu là hợp đồng identity/equality, không phải ép mọi class thành record.

## 6. Final class tự viết equals/hashCode

Không cần record vẫn có thể tạo value object tốt:

~~~java
import java.util.Objects;

public final class SkuKey {
    private final String tenantCode;
    private final String catalogCode;
    private final String skuCode;

    public SkuKey(String tenantCode, String catalogCode, String skuCode) {
        this.tenantCode = Objects.requireNonNull(tenantCode);
        this.catalogCode = Objects.requireNonNull(catalogCode);
        this.skuCode = Objects.requireNonNull(skuCode);
    }

    public String tenantCode() { return tenantCode; }
    public String catalogCode() { return catalogCode; }
    public String skuCode() { return skuCode; }

    @Override
    public boolean equals(Object object) {
        if (this == object) return true;
        if (!(object instanceof SkuKey other)) return false;
        return tenantCode.equals(other.tenantCode)
            && catalogCode.equals(other.catalogCode)
            && skuCode.equals(other.skuCode);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantCode, catalogCode, skuCode);
    }
}
~~~

Class final tránh việc subclass tự thay đổi equality policy. Field final chứa String bất biến giúp hash không đổi theo lifecycle của đối tượng.

### 6.1. Những gì phải review

- Các field equals và hashCode có **cùng ngữ nghĩa**.
- Field có thể null không? Có dùng Objects.equals nhất quán không?
- Có field mutable không?
- Subclass/proxy có thể thay đổi kiểu thực tế không?
- Có điều kiện nào khiến hai instance cùng ID nhưng khác trạng thái bị coi là khác entity không?
- Có field nhạy cảm được đưa vào toString do công cụ tự sinh không?

Nếu đổi tập field của equals, phải rà lại hashCode, test và mọi nơi object được dùng làm key.

## 7. HashSet/HashMap: phép kiểm tra thực tế

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

Sku first = new Sku("VN-01", "MAIN", "P0012");
Sku sameValue = new Sku("VN-01", "MAIN", "P0012");

Set<Sku> seen = new HashSet<>();
seen.add(first);
seen.add(sameValue);
System.out.println(seen.size()); // 1

Map<Sku, Integer> stock = new HashMap<>();
stock.put(first, 10);
System.out.println(stock.get(sameValue)); // 10
~~~

Một test chỉ kiểm tra first.equals(sameValue) có thể bỏ sót bug **quên override hashCode**. Vì vậy cần test cả:

- So equals hai chiều.
- Hash của hai đối tượng bằng nhau.
- Set không tạo hai phần tử khi key tương đương.
- Map đọc được bằng instance khác có cùng value.

**HashSet không bảo đảm thứ tự thêm.** Nếu cần thứ tự dòng đơn, mô hình hóa lineNo/position và chọn collection phù hợp; đừng suy thứ tự từ hash.

## 8. Mutable key: lỗi mất tra cứu sau khi sửa

~~~java
import java.util.Objects;

public final class MutableSkuKey {
    private String code;

    public MutableSkuKey(String code) {
        this.code = code;
    }

    public void setCode(String code) {
        this.code = code;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof MutableSkuKey that
            && Objects.equals(code, that.code);
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(code);
    }
}
~~~

~~~java
Map<MutableSkuKey, String> map = new HashMap<>();
MutableSkuKey key = new MutableSkuKey("P0012");

map.put(key, "Bánh dinh dưỡng");
key.setCode("P0099");

String value = map.get(key); // Có thể không tra thấy.
~~~

Entry đã được định vị theo hash cũ. Nếu code đổi làm hash khác, lookup có thể tìm sai bucket. Không cần chứng minh mọi trường hợp đều trả null; bản thân khả năng thay hash **khi key nằm trong map** đã vi phạm giả định vận hành.

### 8.1. Chính sách đúng

- Dùng **immutable value object** làm key.
- Khi cần đổi business code, tạo key mới rồi xóa entry cũ/thêm entry mới.
- Với entity có status, name, address mutable, không đưa chúng vào equality theo identity.
- Khi nghiệp vụ cho phép đổi mã sản phẩm, dùng **durable entity identity** và **alias/history** thay vì sửa key đang tham chiếu.

## 9. Immutability khác domain invariant

Một đối tượng có thể immutable nhưng **sai nghiệp vụ**, ví dụ OrderId chứa UUID null hoặc ValidInterval có start sau end.

| Loại bảo đảm | Ví dụ | Kiểm chứng |
|---|---|---|
| Reference không đổi | final field | Không gán lại reference |
| Nội dung không đổi | List, Map, byte[] | Defensive copy và immutable element |
| Giá trị hợp lệ | quantity > 0 | Constructor/method guard |
| Identity ổn định | orderId | Không thay khi status đổi |
| Trạng thái đúng | CONFIRMED cần ít nhất một line | Workflow invariant |
| Quan hệ đúng | orderLine thuộc đúng order/tenant | FK/aggregate validation |
| Thời gian đúng | validFrom < validTo | Value object/DB constraint |
| Không overlap | Hai version cùng identity không giao nhau | Transaction/EXCLUDE |
| Không mất tiền | Tổng refund không vượt payment | Giao dịch nhiều hàng |

**final không đồng nghĩa deep immutable.** Một field final trỏ tới ArrayList vẫn quan sát được các thay đổi trong list. Đồng thời một entity có thể mutable nhưng giữ **identity bất biến** và mọi domain invariant trong các chuyển trạng thái.

## 10. Record là bất biến nông, không tự copy collection

Ví dụ nguy hiểm:

~~~java
import java.util.List;

public record OrderSnapshot(List<String> skuCodes) {
}
~~~

~~~java
List<String> input = new java.util.ArrayList<>();
input.add("P0012");
OrderSnapshot snapshot = new OrderSnapshot(input);
input.add("P0099");

// Nội dung snapshot.skuCodes() có thể thay đổi từ bên ngoài.
~~~

Record chứa tham chiếu final tới list nhưng **list vẫn mutable**. Vì List.equals/hashCode dựa trên nội dung, hashCode của record cũng có thể đổi theo thời gian.

### 10.1. Copy khi tạo

~~~java
import java.util.List;
import java.util.Objects;

public record OrderSnapshot(List<String> skuCodes) {
    public OrderSnapshot {
        Objects.requireNonNull(skuCodes, "skuCodes");
        skuCodes = List.copyOf(skuCodes);
    }
}
~~~

Khi input là List mutable, List.copyOf tạo snapshot không thể sửa qua API List. Vì phần tử là **String bất biến**, ví dụ đủ để có value object bất biến theo thành phần này.

~~~java
List<String> input = new java.util.ArrayList<>();
input.add("P0012");
OrderSnapshot snapshot = new OrderSnapshot(input);

input.add("P0099"); // Không đổi snapshot.
snapshot.skuCodes().add("X"); // UnsupportedOperationException
~~~

**List.copyOf không copy sâu từng phần tử**. Nếu List chứa MutableAddress, phần tử đó vẫn có thể bị sửa. Phải dùng immutable element hoặc tạo bản sao sâu theo nhu cầu nghiệp vụ. List.copyOf không chấp nhận null element; chính sách này phải được xác nhận.
## 11. Mảng: record mặc định không so nội dung byte[]

Xét:

~~~java
public record BinaryTag(byte[] bytes) {
}
~~~

Vấn đề thứ nhất: mảng mutable, caller có thể sửa sau constructor hoặc lấy qua accessor rồi sửa. Vấn đề thứ hai: hai byte[] có cùng nội dung nhưng là **hai mảng khác nhau**, và mặc định mảng so bằng Object.equals theo tham chiếu.

Nếu BinaryTag là value object theo **nội dung byte**, cần thực hiện cả copy và equality theo nội dung:

~~~java
import java.util.Arrays;
import java.util.Objects;

public record BinaryTag(byte[] bytes) {
    public BinaryTag {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof BinaryTag that
            && Arrays.equals(bytes, that.bytes);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(bytes);
    }
}
~~~

- Clone trong constructor ngăn caller sửa nội bộ qua mảng gốc.
- Clone trong accessor ngăn sửa nội bộ qua mảng trả về.
- Arrays.equals so từng byte; Arrays.hashCode dựa trên nội dung tương ứng.
- Cần thêm constraint độ dài/format nếu business key phải có số byte cố định.

Dùng **Objects.equals(bytesA, bytesB)** không phải so nội dung mảng: nó vẫn dựa vào equals của array object.

## 12. Chuẩn hóa mã và equality phải theo hợp đồng nguồn

Hai chuỗi:

~~~text
"P0012"
"p0012"
~~~

có thể là cùng hoặc khác SKU tùy quy tắc hệ nguồn. Đừng tự dùng equalsIgnoreCase hoặc lower-case toàn bộ nếu mã thực sự phân biệt hoa/thường.

Nếu một namespace business **quy định không phân biệt hoa/thường**, có thể chuẩn hóa ngay ở constructor:

~~~java
import java.util.Locale;
import java.util.Objects;

public record CaseInsensitiveCode(String value) {
    public CaseInsensitiveCode {
        Objects.requireNonNull(value, "value");
        value = value.trim().toUpperCase(Locale.ROOT);
        if (value.isEmpty()) {
            throw new IllegalArgumentException("code cannot be blank");
        }
    }
}
~~~

Khi đó record equals/hashCode dùng một **giá trị đã chuẩn hóa**. Nhưng đây chỉ là ví dụ cho một domain có chính sách như vậy.

### 12.1. Những thông tin phải chốt trước khi chuẩn hóa

- Có phân biệt hoa/thường không?
- Khoảng trắng đầu/cuối có ý nghĩa không?
- Số 0 đầu trong "0012" có ý nghĩa không?
- Có cần Unicode normalization không?
- Các nguồn có cùng chuẩn mã hay có namespace khác nhau?
- Database collation/unique index có so tương đương Java không?
- Khi nhập dữ liệu cũ, có xung đột được tạo ra do chuẩn hóa không?

Đặc biệt, chuyển **"0012"** thành integer 12 rồi chuyển lại string là sai nếu mã có số 0 đầu là định danh quan trọng.

### 12.2. Bình đẳng của String không tự phản ánh collation SQL

String.equals so theo các giá trị String của Java, còn SQL UNIQUE có ngữ nghĩa tùy kiểu/collation và cấu hình. Nếu ứng dụng coi "AbC" bằng "abc" nhưng database UNIQUE phân biệt, hai đường ghi có thể tạo hai record Java coi cùng key. Ngược lại, database có thể từ chối hai mã Java coi khác.

Nên chọn một canonicalization rõ và kiểm tra **round-trip Java → database → Java** cùng các trường hợp Unicode, chữ hoa/thường và khoảng trắng.

## 13. BigDecimal, scale và tiền tệ

BigDecimal.equals không chỉ xét giá trị số học mà còn xét scale:

~~~java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("10.0");
BigDecimal b = new BigDecimal("10.00");

System.out.println(a.equals(b));            // false
System.out.println(a.compareTo(b) == 0);    // true
~~~

Trong môi trường thuần số học, hai số đều đại diện số lượng 10. Nhưng với BigDecimal, equals coi hai object khác do scale. **compareTo không nhất quán với equals** ở các trường hợp như vậy, nên HashSet và TreeSet dùng thứ tự tự nhiên có thể cho số phần tử khác nhau.

### 13.1. Thiết kế Money theo chính sách của domain

Nếu hệ thống chốt rằng hai giá trị tiền có cùng số học và cùng currency là bằng nhau:

~~~java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
        amount = amount.stripTrailingZeros();
    }
}
~~~

Khi dùng Money:

- 10.0 VND và 10.00 VND trở thành cùng giá trị sau chuẩn hóa.
- 10 USD và 10 VND **không bằng nhau** vì currency khác.
- stripTrailingZeros có thể tạo scale âm hoặc dạng số khoa học khi hiển thị; format báo cáo là bài toán riêng.
- Nếu nghiệp vụ cần **scale cố định theo currency**, phải chốt precision/rounding/đơn vị tiền trước khi tạo Money.
- Nếu là **số đo** với mức chính xác của phép đo, scale có thể mang ý nghĩa và không nên bị loại bỏ tùy tiện.

Không dùng double cho tiền nếu cần số học decimal chính xác và quy tắc làm tròn rõ.

### 13.2. double và khoảng sai số

Double có NaN, Infinity, +0.0/-0.0 và sai số biểu diễn nhị phân. Nếu một value object chứa double và dùng làm key, phải định nghĩa rõ các trường hợp đặc biệt.

Không dùng phép so “chênh dưới epsilon” làm equals vì có thể phá bắc cầu. Nếu nghiệp vụ cần gộp các mẫu đo trong một ngưỡng, dùng một hàm so gần nhau riêng hoặc chuẩn hóa thành **bucket chính xác** trước khi xây key.

## 14. Thời gian và ý nghĩa của bình đẳng

Hai biểu diễn có thể cùng **thời điểm tuyệt đối**:

~~~java
import java.time.OffsetDateTime;

OffsetDateTime local = OffsetDateTime.parse(
    "2026-07-01T07:00:00+07:00"
);
OffsetDateTime utc = OffsetDateTime.parse(
    "2026-07-01T00:00:00Z"
);

System.out.println(local.equals(utc)); // false
System.out.println(
    local.toInstant().equals(utc.toInstant())
); // true
~~~

Nếu domain key đại diện một **instant tuyệt đối**, chuẩn hóa bằng Instant là hợp lý. Nhưng nếu key đại diện **ngày lịch cửa hàng**, múi giờ kinh doanh và ngày địa phương lại quan trọng. Một LocalDate hoặc ZonedDateTime có thể mang nghĩa khác nhau.

### 14.1. Bất biến của khoảng nửa mở

Một interval dùng [start, endExclusive) để tránh chồng lấn tại biên:

~~~java
import java.time.Instant;
import java.util.Objects;

public record ValidInterval(Instant start, Instant endExclusive) {
    public ValidInterval {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(endExclusive, "endExclusive");

        if (!start.isBefore(endExclusive)) {
            throw new IllegalArgumentException(
                "start must precede endExclusive"
            );
        }
    }

    public boolean contains(Instant instant) {
        Objects.requireNonNull(instant);
        return !instant.isBefore(start)
            && instant.isBefore(endExclusive);
    }
}
~~~

Khoảng [01/07,01/08) chứa đúng đầu ngày 01/07, không chứa đầu ngày 01/08. Constructor bảo đảm **một khoảng hợp lệ**, nhưng không bảo đảm hai version cùng product không overlap; invariant liên hàng phải được bảo vệ ở aggregate/database.

### 14.2. Các mốc khác nhau không được gộp

- eventTime: lúc sự kiện xảy ra.
- receivedAt: lúc server nhận.
- validFrom/validTo: thời gian có hiệu lực nghiệp vụ.
- knownFrom/knownTo: khoảng hệ thống từng chấp nhận thông tin.
- createdAt: lúc tạo bản ghi kỹ thuật.

Không lấy ID có timestamp (UUIDv7/Snowflake) làm nguồn thời gian nghiệp vụ, và không dùng receivedAt thay cho valid time nếu thiết kế có correction hồi tố.

## 15. Kế thừa có thể phá tính đối xứng

Giả sử lớp cha coi mọi BaseProduct có cùng code là bằng nhau:

~~~java
public class BaseProduct {
    protected final String code;

    public BaseProduct(String code) {
        this.code = java.util.Objects.requireNonNull(code);
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof BaseProduct that
            && code.equals(that.code);
    }

    @Override
    public int hashCode() {
        return code.hashCode();
    }
}
~~~

Một subclass ColoredProduct thêm color và override equals để chỉ so với ColoredProduct cùng code/color. Khi đó có thể xảy ra:

~~~text
base.equals(colored)  = true
colored.equals(base)  = false
~~~

Đây là lỗi **symmetry**. Nếu một subclass mới đưa thêm field vào equality, còn lớp cha không biết field ấy, cần xem lại toàn bộ chính sách.

Các lựa chọn:

- Với value object, ưu tiên **record/final class** để khóa equality policy.
- Dùng **composition** thay vì mở rộng inheritance chỉ để bổ sung component.
- Với hierarchy bắt buộc, định nghĩa equality chung cho các loại và test symmetric/transitive toàn bộ subtype.
- getClass() có thể bảo vệ khác loại nhưng có đánh đổi khi ORM tạo proxy/subclass động.

Không có một snippet equals phù hợp cho mọi entity hierarchy.

## 16. Entity bình đẳng theo danh tính, không theo toàn bộ trạng thái

Một Order trải qua:

~~~text
orderId = O100
DRAFT -> CONFIRMED -> SHIPPED

totalAmount có thể được điều chỉnh theo chính sách.
~~~

Đây vẫn là **cùng một đơn**. Nếu equals dựa vào orderStatus, lines hoặc totalAmount, mỗi lần cập nhật trạng thái lại làm thay đổi equality/hash.

Với entity, quy tắc thường phù hợp là **danh tính ổn định**:

> Hai SalesOrder bằng nhau nếu chúng biểu diễn cùng một đơn đã được định danh trong namespace thích hợp.

Value object cho ID:

~~~java
import java.util.Objects;
import java.util.UUID;

public record OrderId(UUID value) {
    public OrderId {
        Objects.requireNonNull(value, "orderId");
    }
}
~~~

Một entity có thể mutable về trạng thái mà vẫn giữ orderId bất biến. Khi cần so **snapshot nội dung**, dùng phương thức compareContent hoặc DTO bất biến riêng; không đổi nghĩa entity.equals thành so toàn bộ trạng thái.

### 16.1. Không đưa quan hệ hai chiều vào equals/hashCode

Nếu Order.equals duyệt tất cả OrderLine, còn OrderLine.equals duyệt lại Order, có thể tạo đệ quy vô hạn hoặc load lazy graph ngoài dự kiến. Việc so toàn bộ graph cũng đắt và thay đổi theo thời gian.

Đối với entity ORM, cần thiết kế field thuộc identity rõ ràng, không tự động so toàn bộ relation fields.

## 17. JPA/Hibernate: ID được cấp sau persist là rủi ro riêng

Entity ORM dùng @GeneratedValue có thể tồn tại qua các giai đoạn:

~~~text
Transient: id = null
Persisted: id = 123
Detached: id = 123
Reloaded:  một instance khác, id = 123
~~~

Sai lầm thứ nhất: xem hai entity transient đều có id null là bằng nhau. Sai lầm thứ hai: dùng hashCode theo id khi id chuyển null → 123 trong lúc entity đang nằm trong HashSet.

### 17.1. Ba hướng thiết kế cần đánh giá

**A. Không override equals/hashCode:** entity dùng reference equality. Đơn giản trong một vòng đời instance, nhưng hai instance ở hai persistence context có cùng row database không mặc nhiên bằng nhau.

**B. ID được cấp trước persist:** cấp UUID/durable ID tại lúc tạo entity. Nếu có contract ổn định, equality theo ID có thể không đổi khi entity được persist.

**C. Persisted-ID equality với quy tắc đặc biệt:** hai entity có **id khác null và bằng nhau** có thể được coi cùng entity; transient entity chỉ bằng chính tham chiếu. Hash strategy phải tránh thay đổi khi ID xuất hiện, hoặc bảo đảm entity không làm key trước persist. Một cách là hash ổn định theo entity type nhưng điều đó có thể gây collision nhiều; còn phải xử lý ORM proxy.

Không dùng một snippet JPA bất kỳ mà không kiểm thử với framework, proxy và lifecycle thực tế.

### 17.2. Kiểm thử với ORM thật

- Hai entity transient khác nhau dù id đều null.
- Một entity trước/sau persist không làm hỏng HashSet.
- Detached và reloaded entity có equality theo chính sách đã chọn.
- Proxy và object thật không vi phạm symmetric/transitive.
- Update status/name không thay đổi identity.
- Lazy collection không bị load chỉ vì gọi equals/hashCode.
- Không có vòng đệ quy qua hai chiều quan hệ.

## 18. Phân biệt identity của sản phẩm với identity của phiên bản SCD2

Trong mô hình thời gian:

~~~text
Product logical identity:
  productId = P01

Product versions:
  versionKey = 1001, category = FOOD, valid [01/01, 01/08)
  versionKey = 1002, category = GIFT, valid [01/08, +∞)
~~~

Hai version có cùng productId nhưng **khác hàng version**, nên cần hai loại khóa:

~~~java
public record ProductId(
    String tenantCode,
    String sourceSystem,
    String productCode
) {
}

public record ProductVersionId(long value) {
}
~~~

Map theo ProductId hữu ích để tra sản phẩm logic; Map theo ProductVersionId hữu ích để tra phiên bản đã được fact tham chiếu. Nếu Map theo ProductId chứa cả hai version, version sau có thể ghi đè version trước.

### 18.1. validFrom không chắc là version key bền vững

Nếu dùng (productId, validFrom) làm khóa phiên bản, correction hồi tố có thể sửa validFrom và làm thay đổi key. Khi yêu cầu giữ revision/audit, cân nhắc surrogate version ID bất biến và các trường valid/known time riêng.

Java equals không tự ngăn **hai khoảng hiệu lực cùng product overlap**. Đó là constraint giữa các row/phiên bản, cần transactional validation hoặc EXCLUDE.

## 19. Java equality phải tương thích với UNIQUE của database

Giả sử business key SKU là **(tenant_code, catalog_code, sku_code)**:

~~~sql
CREATE TABLE catalog_sku (
    sku_id uuid PRIMARY KEY,
    tenant_code text NOT NULL,
    catalog_code text NOT NULL,
    sku_code text NOT NULL,

    CONSTRAINT uq_catalog_sku_business
        UNIQUE (tenant_code, catalog_code, sku_code)
);
~~~

Value object Sku ở phần 5 có đúng ba component. Nhưng không thể suy **Java.equals và SQL UNIQUE luôn giống nhau**.

| Điểm khác biệt | Java | Database |
|---|---|---|
| Chữ hoa/thường | String.equals phân biệt | Collation/type/index có thể khác |
| Khoảng trắng | String so theo nội dung | CHAR/collation/normalization có thể khác |
| Unicode | String so chuỗi code units | Collation/normalization có thể khác |
| Null | Objects.equals(null,null) là true | UNIQUE trên cột nullable có ngữ nghĩa riêng |
| Decimal | BigDecimal.equals xét scale | NUMERIC thường có quy tắc so số học |
| Timestamp | OffsetDateTime khác offset | timestamptz so instant |
| Multi-tenant | Có thể bỏ sót tenant ở equals | UNIQUE composite có thể chứa tenant |
| Soft delete | Entity vẫn có ID | Partial unique index có thể chỉ áp active rows |

### 19.1. Java Set không thay thế UNIQUE thật

Hai worker có thể cùng kiểm tra “SKU P0012 chưa tồn tại” rồi đồng thời INSERT. Một HashSet trong mỗi tiến trình không biết trạng thái của tiến trình kia.

Database cần UNIQUE đúng phạm vi, transaction xử lý conflict và các ràng buộc khác. Validation ở service cung cấp thông báo sớm, nhưng không thay thế bảo vệ ở nơi ghi có thẩm quyền.

### 19.2. Mẫu kiểm thử round-trip

Với mỗi business key mẫu:

1. Tạo immutable key Java.
2. Serialize/persist theo schema.
3. Đọc lại và tái tạo value object.
4. Xác minh equality/hash như contract.
5. Thử insert duplicate theo cùng tenant/collation.
6. Thử cùng code ở tenant khác, nếu business cho phép.
7. Thử chuỗi hoa/thường, Unicode, khoảng trắng và số 0 đầu.

Nếu Java coi hai key bằng nhau còn database chấp nhận hai hàng, hoặc ngược lại, cần sửa **hợp đồng chuẩn hóa hoặc constraint**, không chỉ sửa test cho qua.

## 20. Domain invariant có thể vượt quá một object

equals/hashCode chỉ giải quyết một phần của kiểm chứng mô hình. Các điều kiện sau không thể bảo vệ bằng equality của một object riêng:

- CONFIRMED Order phải có ít nhất một OrderLine.
- SUM(successfulRefund) không vượt capturedAmount cho phép.
- Hai phiên bản sản phẩm không overlap valid_period.
- Một dòng bán không được gắn phiên bản product sai ngày.
- Một SKU có tối đa một primary category tại một ngày.
- Một event chỉ được xử lý một lần theo requestId trong hệ có nhiều worker.

### 20.1. Một invariant theo trạng thái

~~~java
import java.util.List;
import java.util.Objects;

public final class OrderDraft {
    private final OrderId orderId;
    private final List<OrderItem> items;

    public OrderDraft(OrderId orderId, List<OrderItem> items) {
        this.orderId = Objects.requireNonNull(orderId);
        this.items = List.copyOf(items);
    }

    public void validateBeforeConfirm() {
        if (items.isEmpty()) {
            throw new IllegalStateException(
                "confirmed order must contain at least one line"
            );
        }
    }
}
~~~

Trong hệ thống thật, **OrderItem** phải được định nghĩa là kiểu immutable hoặc copy sâu; đoạn trên tập trung vào quy tắc tối thiểu dòng. Ngay cả khi validateBeforeConfirm trả thành công, transaction xác nhận vẫn cần kiểm tra dữ liệu **dưới điều kiện đồng thời có thẩm quyền**.

### 20.2. Phân công trách nhiệm

| Tầng | Bảo vệ |
|---|---|
| Value-object constructor | Miền giá trị, format, tính bất biến thành phần |
| Aggregate/domain method | Chuyển trạng thái và quy tắc nội bộ aggregate |
| Database constraint | PK/FK/UNIQUE/CHECK/EXCLUDE |
| Transaction/locking/version | Invariant liên hàng và ghi đồng thời |
| ETL/CDC/reconciliation | Dữ liệu nhiều nguồn, đến muộn, correction |
| API authorization | Quyền và phạm vi tenant/actor |

Một mô hình vững chắc không đặt toàn bộ trách nhiệm vào một phương thức equals.
## 21. Kiểm thử JUnit 5 cho hợp đồng equality

Kiểm thử chỉ xác minh a.equals(b) có thể bỏ sót hashCode, symmetry hoặc việc Set không tìm thấy key. Một test class đầy đủ nên kiểm tra cả hành vi collection. Ví dụ dưới đây dùng **Java 17 và JUnit Jupiter**; giả định record Sku ở phần 5 nằm cùng package hoặc được import.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

class SkuTest {

    @Test
    void equalKeysFollowObjectContract() {
        Sku a = new Sku("VN-01", "MAIN", "P0012");
        Sku b = new Sku("VN-01", "MAIN", "P0012");
        Sku c = new Sku("VN-01", "MAIN", "P0012");

        assertNotSame(a, b);
        assertEquals(a, a); // reflexive

        assertEquals(a, b);
        assertEquals(b, a); // symmetric

        assertEquals(b, c);
        assertEquals(a, c); // transitive

        assertEquals(a.hashCode(), b.hashCode());
        assertFalse(a.equals(null));
    }

    @Test
    void allBusinessKeyPartsAffectEquality() {
        Sku base = new Sku("VN-01", "MAIN", "P0012");

        assertNotEquals(base, new Sku("VN-02", "MAIN", "P0012"));
        assertNotEquals(base, new Sku("VN-01", "ALT", "P0012"));
        assertNotEquals(base, new Sku("VN-01", "MAIN", "P0013"));
    }

    @Test
    void hashSetAndHashMapRecognizeEquivalentInstances() {
        Sku a = new Sku("VN-01", "MAIN", "P0012");
        Sku b = new Sku("VN-01", "MAIN", "P0012");

        Set<Sku> keys = new HashSet<>();
        keys.add(a);
        keys.add(b);

        assertEquals(1, keys.size());
        assertTrue(keys.contains(b));

        Map<Sku, Integer> stock = new HashMap<>();
        stock.put(a, 10);
        assertEquals(Integer.valueOf(10), stock.get(b));
    }

    @Test
    void rejectsNullAndBlankComponents() {
        assertThrows(NullPointerException.class,
            () -> new Sku(null, "MAIN", "P0012"));

        assertThrows(IllegalArgumentException.class,
            () -> new Sku("VN-01", "MAIN", " "));
    }
}
~~~

### 21.1. Test tính nhất quán của hash

~~~java
@Test
void immutableSkuHasStableHash() {
    Sku sku = new Sku("VN-01", "MAIN", "P0012");
    int before = sku.hashCode();

    for (int i = 0; i < 100; i++) {
        assertEquals(before, sku.hashCode());
    }
}
~~~

Một vòng lặp hash ổn định **chưa chứng minh bất biến sâu** nếu object có collection mà test chưa sửa từ bên ngoài. Nên có test aliasing riêng.

### 21.2. Không test “hai key khác nhau bắt buộc có hash khác nhau”

Hash collision **được phép**. Do đó:

~~~text
assertNotEquals(a, b)
không có nghĩa
assertNotEquals(a.hashCode(), b.hashCode())
~~~

Một test yêu cầu mọi cặp key khác nhau có hash khác sẽ sai hợp đồng. Thay vào đó, có thể đo **phân phối hash** trên tập dữ liệu đại diện như một bài test hiệu năng/chất lượng, không coi collision đơn lẻ là bug.

## 22. Kiểm thử defensive copy và bất biến của record

Với OrderSnapshot ở phần 10:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderSnapshotTest {

    @Test
    void isNotAffectedByMutableInput() {
        List<String> input = new ArrayList<>();
        input.add("P0012");

        OrderSnapshot snapshot = new OrderSnapshot(input);
        input.add("P0099");

        assertEquals(List.of("P0012"), snapshot.skuCodes());
    }

    @Test
    void accessorDoesNotExposeMutableInternalState() {
        OrderSnapshot snapshot = new OrderSnapshot(List.of("P0012"));

        assertThrows(UnsupportedOperationException.class,
            () -> snapshot.skuCodes().add("P0099"));
    }

    @Test
    void equivalentContentHasEqualHash() {
        OrderSnapshot a = new OrderSnapshot(List.of("A", "B"));
        OrderSnapshot b = new OrderSnapshot(
            new ArrayList<>(List.of("A", "B"))
        );

        assertEquals(a, b);
        assertEquals(a.hashCode(), b.hashCode());
    }
}
~~~

### 22.1. Kiểm thử wrapper byte[]

~~~java
@Test
void binaryTagUsesDefensiveCopiesAndContentEquality() {
    byte[] source = {1, 2, 3};
    BinaryTag first = new BinaryTag(source);
    BinaryTag second = new BinaryTag(new byte[] {1, 2, 3});

    source[0] = 9;
    byte[] exposed = first.bytes();
    exposed[1] = 8;

    assertArrayEquals(new byte[] {1, 2, 3}, first.bytes());
    assertEquals(first, second);
    assertEquals(first.hashCode(), second.hashCode());
}
~~~

Test này cần được đặt trong một test class có import JUnit 5 Assertions và Test, cùng kiểu BinaryTag phần 11. Nó kiểm tra cả hai đường rò tham chiếu, không chỉ Arrays.equals.

### 22.2. Kiểm thử boundary thời gian

~~~java
@Test
void validIntervalIsHalfOpenAndRejectsInvalidBounds() {
    var start = java.time.Instant.parse("2026-07-01T00:00:00Z");
    var end = java.time.Instant.parse("2026-08-01T00:00:00Z");

    assertThrows(IllegalArgumentException.class,
        () -> new ValidInterval(start, start));
    assertThrows(IllegalArgumentException.class,
        () -> new ValidInterval(end, start));

    ValidInterval interval = new ValidInterval(start, end);
    assertTrue(interval.contains(start));
    assertFalse(interval.contains(end));
}
~~~

Không thay biên phải bằng 23:59:59.999 rồi mong xử lý mọi precision. Quy tắc [from,to) cần nhất quán giữa Java và SQL.

## 23. Property-based testing: kiểm tra hợp đồng trên nhiều giá trị

Unit test với vài ví dụ tốt nhưng có thể bỏ sót các mã Unicode, ký tự biên, decimal scale, timezone hoặc namespace. **Property-based testing** sinh nhiều dữ liệu rồi xác minh một tập thuộc tính của kiểu.

Có thể dùng thư viện như **jqwik** hoặc **QuickTheories** nếu dự án đã chọn. Để minh họa ý tưởng bằng Java thuần, có thể dùng vòng lặp có seed xác định:

~~~java
import java.util.Random;

Random random = new Random(20261122L);

for (int i = 0; i < 10_000; i++) {
    String tenant = "T-" + random.nextInt(20);
    String skuCode = "P-" + random.nextInt(10_000);

    Sku a = new Sku(tenant, "MAIN", skuCode);
    Sku b = new Sku(tenant, "MAIN", skuCode);
    Sku c = new Sku(tenant, "MAIN", skuCode);

    if (!(a.equals(b) && b.equals(a)
            && b.equals(c) && a.equals(c))) {
        throw new AssertionError("equality contract broken");
    }
    if (a.hashCode() != b.hashCode()) {
        throw new AssertionError("hash contract broken");
    }
}
~~~

Đây là đoạn **thuật toán minh họa** đặt trong một phương thức hoặc test context, không phải một file Java hoàn chỉnh. Khi dùng JUnit, nên dùng **Assertions** thay vì Java assert, vì keyword assert có thể bị tắt khi JVM không bật assertions.

### 23.1. Thuộc tính nên sinh và kiểm tra

1. Cùng value đã chuẩn hóa → equals true và cùng hash.
2. Khác thành phần business key → equals false theo chính sách.
3. Refexive, symmetric, transitive và non-null.
4. Set/Map nhận dạng instance tương đương.
5. Tạo object từ collection mutable rồi sửa collection gốc không đổi object.
6. Lấy accessor rồi thử sửa không đổi object.
7. Serialize/deserialize value object vẫn bảo toàn nghĩa.
8. Database round-trip không đổi business key.
9. Hai instance entity khác status nhưng cùng identity vẫn cùng entity theo policy.
10. Hai ProductVersion khác version ID không bị gộp.

### 23.2. Sinh dữ liệu biên

- Null, blank và whitespace.
- Ký tự Unicode có thể biểu diễn theo dạng chuẩn khác nhau.
- Mã có số 0 ở đầu, chữ hoa/thường.
- BigDecimal 0.0, 0.00, số âm và large precision.
- double +0.0/-0.0, NaN, Infinity nếu miền dữ liệu cho phép.
- Timestamp cùng Instant nhưng offset khác.
- Collection rỗng, một phần tử, nhiều phần tử, duplicate.
- byte[] rỗng, có giá trị 0 và độ dài lớn.
- Product identity giống nhau nhưng version khác.
- Entity transient, persisted, detached và proxied.

Không dùng dữ liệu khách thật để tăng “tính thực tế” của bộ test.

## 24. Kiểm thử entity ở nhiều giai đoạn ORM

Nếu dùng JPA/Hibernate, cần kiểm thử với **persistence context thực**, không chỉ new Entity(...).

| Giai đoạn | Tình huống | Bất biến cần giữ |
|---|---|---|
| Transient | Hai entity mới có id null | Không bị coi cùng entity chỉ vì cùng null |
| Persisted | ID được cấp sau INSERT | Hash/equality không làm mất tra cứu trong collection |
| Managed | Entity đã thuộc persistence context | Identity policy được giữ |
| Detached | Entity rời session | Identity không mất |
| Reloaded | Instance khác đọc cùng hàng DB | Kết quả equality theo thiết kế được giữ |
| Proxied | ORM tạo subtype/proxy | Không vi phạm symmetry/transitivity |
| Updated | Status/name đổi | Identity ổn định |
| Archived | Soft delete hoặc ngừng hoạt động | Không tái sử dụng ID trái chính sách |

Nếu chọn reference equality, hãy kiểm tra rõ những API nào không được kỳ vọng equals giữa detached/reloaded objects. Nếu chọn ID equality, kiểm tra **ID lifecycle, proxy handling và hash stability**.

### 24.1. Cẩn trọng với công cụ sinh code

Annotation hoặc framework sinh equals/hashCode trên **mọi field** của entity có thể dẫn đến:

- Lặp đệ quy qua quan hệ hai chiều.
- Kích hoạt lazy loading ngoài ý muốn.
- Hash đổi khi status/collection đổi.
- Hai đơn khác ID nhưng cùng nội dung bị xem là một.
- Lộ field nhạy cảm khi toString được sinh tự động.

Hãy kiểm tra code thực sự được sinh và khai báo rõ identity fields.

## 25. Kiểm thử tích hợp Java và PostgreSQL

Test value object chỉ kiểm chứng Java; invariant unique/concurrency ở database vẫn cần kiểm thử riêng.

Giả sử khóa SKU là:

~~~sql
CREATE TABLE catalog_sku (
    sku_id uuid PRIMARY KEY,
    tenant_code text NOT NULL,
    catalog_code text NOT NULL,
    sku_code text NOT NULL,
    CONSTRAINT uq_catalog_sku_business
        UNIQUE (tenant_code, catalog_code, sku_code)
);
~~~

### 25.1. Ma trận đối chiếu

| Tình huống | Java | PostgreSQL |
|---|---|---|
| Cùng tenant/catalog/code | equals true | UNIQUE từ chối hàng thứ hai |
| Khác tenant cùng code | equals false | Chấp nhận nếu key theo tenant |
| Khác catalog cùng tenant/code | equals false | Chấp nhận nếu catalog trong key |
| Case khác, nguồn case-sensitive | equals false | Collation/index phải phù hợp |
| Có số 0 đầu | Giữ nguyên | Cột text phải không làm mất mã |
| BigDecimal khác scale | Theo policy Money | NUMERIC/rounding phù hợp |
| Hai product version cùng BK | Khác theo versionId | SCD2 cho phép nếu không overlap |
| Hai khoảng valid overlap | Hai object riêng lẻ vẫn có thể hợp lệ | EXCLUDE/transaction từ chối cặp vi phạm |
| Hai worker ghi cùng SKU | HashSet cục bộ không đủ | UNIQUE + conflict handling |

### 25.2. Test concurrency thay vì chỉ SELECT trước INSERT

Hai worker có thể đồng thời làm:

~~~text
A: SELECT không thấy SKU P0012
B: SELECT không thấy SKU P0012
A: INSERT SKU P0012
B: INSERT SKU P0012
~~~

Nếu chỉ dựa vào Set hoặc SELECT, cả hai đường ghi có thể chấp nhận cùng key. UNIQUE ở DB có thẩm quyền phải bảo vệ cuộc đua, ứng dụng phải xử lý constraint violation hoặc ON CONFLICT đúng.

### 25.3. Mẫu integration test

1. Khởi tạo database test với migration thật.
2. Insert SKU theo business key A.
3. Thử insert duplicate A; kiểm tra bị từ chối đúng constraint.
4. Insert cùng code ở tenant B; kiểm tra được nếu chính sách cho phép.
5. Đọc SKU về Java; kiểm tra equals/hash với key tạo từ request.
6. Test collation/case/Unicode theo chuẩn nguồn.
7. Chạy hai transaction ghi cạnh tranh cùng key.
8. Dùng dữ liệu ProductVersion để thử overlap/gap.
9. Đảm bảo failed transaction không để lại partial state.

Các test chạy bằng database thực tế có giá trị hơn giả lập HashMap nếu mục tiêu là chứng minh ràng buộc dữ liệu bền.

## 26. Dữ liệu phân tán, document, graph và analytical modeling

### 26.1. Định danh qua nhiều tenant và vùng

Hai vùng có thể cùng có local order number 1001. Trong Java, key cần giữ namespace:

~~~java
import java.util.UUID;

public record TenantOrderKey(UUID tenantId, UUID orderId) {
    public TenantOrderKey {
        if (tenantId == null || orderId == null) {
            throw new IllegalArgumentException("Both ID parts required");
        }
    }
}
~~~

Nhưng equality đúng **không tự bảo đảm** UUID global unique giữa database độc lập hoặc ngăn retry tạo hai order ID khác nhau. Cần ID strategy, source identity và idempotency theo phạm vi đúng.

### 26.2. Document model

Một document Order có mảng items. Domain entity dùng **documentId/aggregateId** cho identity; một snapshot DTO có thể so **nội dung** sau defensive copy. Nếu so equality sâu toàn bộ document làm định danh, sửa một item có thể biến order cũ thành “một order khác” trong Set.

### 26.3. Graph model

Một graph Customer–Product có thể có hai cạnh PURCHASED vào hai thời điểm khác nhau. Nếu chỉ lấy endpoints làm equality của event edge, hai lần mua có thể bị gộp. Cần xác định grain: **quan hệ trạng thái hiện hành** hay **sự kiện mua hàng có eventId/time**.

### 26.4. Analytical modeling

Fact bán hàng có thể dùng sourceLineId; hai fact có cùng quantity và netAmount vẫn khác nhau nếu là hai dòng bán thật. Dimension SCD2 có version ID riêng; nếu Set keyed theo productId thì có thể loại mất phiên bản lịch sử.

**Một phép equals đúng cho ProductId chưa chắc đúng cho ProductVersionId hay SalesLineId.**

## 27. Migration: thay đổi equality là thay đổi hợp đồng dữ liệu

Giả sử ban đầu SKU chỉ unique theo **(catalogCode, skuCode)**. Khi mở đa tenant, key đổi thành **(tenantCode, catalogCode, skuCode)**.

Tác động:

1. Value object thêm tenantCode.
2. equals/hashCode và test thay đổi.
3. HashMap/Set trong cache/dedup cần key mới.
4. UNIQUE index phải đổi scope.
5. API, event payload và các consumer có thể cần tenant.
6. Dữ liệu cũ thiếu tenant phải backfill/quarantine.
7. Redis key, partition key và idempotency scope có thể đổi.
8. Serializer/deserializer và snapshot cũ cần migration.
9. Consumer cũ bỏ tenant có thể dedup sai.
10. Cần versioned contract để tránh hai phiên bản service hiểu key khác nhau trong cùng kỳ triển khai.

Đổi equality không nên bị xem là refactor nội bộ vô hại khi object dùng làm business key trên nhiều hệ.

### 27.1. Khi đổi business code nhưng entity vẫn là một

Nếu sản phẩm P0012 đổi mã thành SKU-2026-12, có thể cần:

~~~text
ProductIdentity: durableProductId ổn định
ProductCodeAlias: sourceSystem + code + validPeriod
ProductVersion: từng phiên bản thuộc tính có versionId
~~~

Định danh entity bằng durableProductId; alias theo code và thời gian; version theo versionId. Không sửa equality của entity thành so tên/mã mutable rồi làm mất lịch sử.

## 28. Những anti-pattern cần phát hiện trong code review

| Anti-pattern | Hậu quả | Hướng sửa |
|---|---|---|
| Chỉ override equals | Hash-based collection hoạt động sai | Override hashCode tương ứng |
| Hash theo status/name mutable | Key thay đổi trong Map | Immutable key hoặc stable entity ID |
| Entity equals toàn bộ fields | Identity sai, lazy load, recursion | Quy tắc identity explicit |
| Hai transient entity null ID đều bằng nhau | Gộp nhầm entity mới | Xử lý transient theo policy |
| Record giữ List mutable | Hash/giá trị đổi qua alias | Copy collection, immutable elements |
| Record giữ byte[] mặc định | Equality theo tham chiếu | Arrays.equals/hashCode và clone |
| Tolerance trong equals | Có thể vi phạm transitive | Approximate comparison riêng |
| BigDecimal.scale bị bỏ qua không nhất quán | 10.0 khác 10.00 ngoài ý định | Canonicalization theo domain |
| So customer theo tên/email | Gộp nhầm cá nhân | Durable identity, crosswalk |
| Bỏ tenant/source khỏi key | Trùng dữ liệu đa nguồn | Composite key có namespace |
| Map keyed ProductId để giữ SCD2 versions | Mất version | ProductVersionId |
| hashCode làm PK database | Collisions | UUID/PK/UNIQUE thực |
| Chỉ test a.equals(b) | Bỏ sót hash contract | Test HashSet/HashMap |
| Set trong service thay UNIQUE DB | Race giữa writer | Constraint + transaction |
| Java normalize nhưng SQL khác | Duplicates/false conflicts | Integration test round-trip |
| getClass mặc định với proxy ORM | Có thể sai equals | Review và test framework-specific |
| toString sinh mọi field PII | Rò dữ liệu vào log | Giới hạn field hiển thị |
| Không version hóa policy equality | Migration/cache/consumer lỗi | ADR, compatibility và backfill |

## 29. Bài thực hành: kiểm chứng mô hình đơn hàng và sản phẩm

Một sàn bán lẻ có các yêu cầu:

- Nhiều tenant dùng cùng mã SKU.
- Product có identity ổn định; category đổi theo SCD2.
- Order được tạo offline rồi đồng bộ bằng UUID.
- CreateOrder có thể gửi lại nhiều lần.
- OrderLine lưu capturedUnitPrice/Currency đã chốt.
- Một Order có thể có hai line cùng SKU nhưng khuyến mại khác.
- Refund có lifecycle riêng.
- Fact bán theo dòng phải tra đúng ProductVersion tại ngày bán.
- Dự án dùng Java 17, PostgreSQL và JUnit 5.

### 29.1. Phần A — Chốt equality policy

Với mỗi kiểu **Sku, ProductIdentity, ProductVersion, SalesOrder, OrderLine, Money, CreateOrderRequestKey, OrderCreatedEvent**, hãy viết:

1. Grain của một instance.
2. Định danh nghiệp vụ/khóa kỹ thuật.
3. Tập field thuộc equality.
4. Những field nào được phép thay đổi.
5. Có thể dùng làm HashMap key/HashSet element không?
6. Constraint database nào bổ trợ?

### 29.2. Phần B — Cài đặt Java

Tạo:

- Sku immutable gồm tenant/catalog/code.
- Money dùng BigDecimal/Currency với quy tắc scale rõ.
- OrderId immutable chứa UUID.
- OrderSnapshot với List defensive copy.
- BinaryTag so nội dung byte array và clone hai chiều.
- ValidInterval chứa biên [from,to).
- ProductVersionId khác ProductId.
- CreateOrderRequestKey có tenant/client/requestId, dùng cho idempotency.

### 29.3. Phần C — Unit, property và integration tests

Kiểm tra:

1. Reflexive, symmetric, transitive, consistent và non-null.
2. Equal-implies-same-hash; HashSet/HashMap nhận instance tương đương.
3. Khác tenant hoặc catalog không bị coi bằng.
4. Mã case/leading zero/Unicode theo chuẩn nguồn.
5. Money 10.0 và 10.00 theo chính sách.
6. Không sửa được snapshot từ input/accessor.
7. Khoảng [01/07,01/08) nhận biên trái, loại biên phải.
8. Hai ProductVersion cùng product nhưng khác version ID không gộp.
9. Entity trước/sau persist không phá hợp đồng hash đã chọn.
10. Hai request CreateOrder trùng key không tạo hai đơn.
11. Hai transaction INSERT SKU trùng cùng lúc chỉ một thành công.
12. SCD2 overlap bị từ chối, fact gắn đúng version tại ngày bán.

### 29.4. SQL khởi điểm

~~~sql
CREATE TABLE sku_identity (
    sku_id uuid PRIMARY KEY,
    tenant_code text NOT NULL,
    catalog_code text NOT NULL,
    sku_code text NOT NULL,
    UNIQUE (tenant_code, catalog_code, sku_code)
);
~~~

**Tiêu chí đạt:** từng kiểu có equality policy rõ; value object bất biến và đúng miền giá trị; Map/Set không mất key; entity giữ identity qua lifecycle; Java và database thống nhất namespace; invariant liên hàng/đồng thời có transaction test.

## 30. Checklist phê duyệt và kết luận

- **Grain:** đây là entity, value, version, snapshot hay event?
- **Identity:** các thành phần key có đầy đủ tenant/source/namespace?
- **equals:** reflexive, symmetric, transitive, consistent, non-null?
- **hashCode:** mọi đối tượng bằng nhau có cùng hash và field hash ổn định?
- **Collections:** HashSet/HashMap có tìm thấy instance tương đương?
- **Record:** List/Map/Set/array và phần tử bên trong có immutable/copy phù hợp?
- **Arrays:** đã dùng Arrays.equals/hashCode khi muốn so nội dung?
- **Numeric:** BigDecimal scale, rounding, currency, NaN và tolerance có policy?
- **Temporal:** Instant/offset/timezone và interval [from,to) đúng?
- **Inheritance:** subclass/proxy có phá symmetry hoặc transitivity không?
- **ORM:** transient, persisted, detached, proxy, ID cấp muộn đã có test?
- **Relationships:** equals có tránh vòng đệ quy và lazy load không?
- **Domain invariants:** constructor/method, transaction và database bổ trợ đủ?
- **Database:** UNIQUE/FK/CHECK/EXCLUDE và Java equality cùng hiểu key không?
- **Distribution:** multiwriter và retry có ID strategy/idempotency đúng phạm vi?
- **History:** ProductId khác ProductVersionId; correction không phá key?
- **Tests:** JUnit, property, integration và concurrency có trường hợp biên?
- **Migration:** thay đổi equality đã xem xét cache, API, event và dữ liệu cũ?
- **Security:** object logging/toString không rò thông tin nhạy cảm?

**Kết luận:** equals, hashCode và tính bất biến là **một phần thực thi của quyết định mô hình hóa**, không chỉ là chi tiết cú pháp Java. Value object cần bình đẳng theo giá trị đã chốt và giữ ổn định sau khi làm khóa; entity cần giữ danh tính khi trạng thái đổi; version cần identity riêng; database phải bảo vệ các ràng buộc giữa nhiều transaction và writer. Khi **ngữ nghĩa nghiệp vụ, kiểu đối tượng Java và lược đồ lưu trữ** thống nhất và được kiểm thử cùng nhau, hệ thống tránh được những lỗi khó phát hiện như gộp nhầm thực thể, lookup thất bại, dedup sai và phá lịch sử dữ liệu.


