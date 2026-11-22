# Rà soát mã được IDE sinh thay vì coi là tự động đúng

**Bối cảnh:** Java Core → Object Contract → Thiết kế hợp đồng.

Các IDE như IntelliJ IDEA, Eclipse và NetBeans có chức năng sinh `equals()`, `hashCode()`, `toString()`, constructor và getter/setter từ danh sách trường. Mã được sinh có thể hợp lệ về **cú pháp** nhưng chưa chắc đúng về **hợp đồng nghiệp vụ**, **tính ổn định** hay **an toàn khi sử dụng**. IDE biết tên và kiểu trường; nó không thể tự suy ra trường nào xác định giá trị, danh tính, trạng thái thay đổi được hoặc dữ liệu bí mật.

Mục tiêu của bài: biết cách đọc và kiểm tra từng quyết định trong mã sinh tự động, phát hiện trường hợp có thể làm hỏng `HashSet` / `HashMap`, gây mất tính đối xứng của `equals`, rò rỉ dữ liệu qua `toString` hoặc thay đổi hợp đồng khi class phát triển.

## 1. Trước khi bấm Generate: phải định nghĩa hợp đồng

Hãy trả lời ba câu hỏi độc lập trước khi yêu cầu IDE sinh mã:

1. **Hai instance được coi là bằng nhau khi nào?** Ví dụ `Money(10, "USD")` và một instance khác cùng số tiền, tiền tệ có thể là cùng *giá trị*; hai đơn hàng có cùng tổng tiền vẫn có thể là *hai thực thể* khác nhau.
2. **Những dữ liệu nào được tham gia so sánh?** Trường `id`, `currency`, `amount`, `version`, `lastUpdated`, cache, mật khẩu hoặc trạng thái giao diện đóng vai trò rất khác nhau. Không có quy tắc “chọn tất cả trường” áp dụng cho mọi class.
3. **Giá trị được dùng làm khóa có ổn định hay không?** Nếu các trường tham gia `equals/hashCode` thay đổi sau khi thêm đối tượng vào collection dựa trên hash, thao tác tìm hoặc xóa có thể không còn thành công.

Một lựa chọn mô hình hợp lý phải được mô tả bằng câu văn dễ kiểm chứng, ví dụ: “Hai `CustomerKey` bằng nhau nếu cùng mã quốc gia, mã khách hàng và tập quyền theo thứ tự đã quy định; token xác thực không xác định khóa”. Sau đó mới sinh mã và so từng điều kiện với câu này.

**Phân biệt value object và entity:** value object thường có `equals` theo các thành phần giá trị đã chọn. Entity thường có danh tính miền nghiệp vụ; nếu ID do cơ sở dữ liệu cấp sau khi lưu, việc đưa thẳng ID có thể thay đổi vào `hashCode` cần được thiết kế đặc biệt. IDE không biết vòng đời entity, proxy ORM hoặc yêu cầu ổn định khóa.

## 2. Bốn mối liên hệ cần luôn giữ đúng

### Hợp đồng `equals(Object)`

Đối với các đối tượng không `null`, theo đặc tả Java, quan hệ bằng nhau phải:

- **Phản xạ:** `x.equals(x)` là `true`.
- **Đối xứng:** `x.equals(y)` và `y.equals(x)` có cùng kết quả.
- **Bắc cầu:** nếu `x.equals(y)` và `y.equals(z)` đều `true` thì `x.equals(z)` phải `true`.
- **Nhất quán:** khi những dữ liệu liên quan không đổi, gọi lặp phải cho cùng kết quả.
- **Không bằng `null`:** `x.equals(null)` là `false`.

Câu lệnh do IDE thường sinh:

```java
if (this == obj) return true;
```

là **tối ưu hợp lệ**: cùng một đối tượng đương nhiên bằng chính nó. Nhưng nếu phần còn lại chỉ dùng `==` để so sánh các trường kiểu `String` hoặc object, đó thường là lỗi so sánh theo danh tính tham chiếu thay vì giá trị.

### Hợp đồng `hashCode()`

Nếu `a.equals(b)` là `true`, **bắt buộc** `a.hashCode() == b.hashCode()`. Chiều ngược lại **không bắt buộc**; va chạm hash là điều bình thường. Nếu override `equals` theo giá trị, gần như luôn phải override `hashCode` tương ứng.

Các trường đưa vào hash phải khớp quan hệ bằng nhau: nếu hai instance bằng nhau khi bỏ qua `description`, thì `hashCode` cũng không được thay đổi theo `description`. Nếu `equals` coi `BigDecimal("1.0")` và `BigDecimal("1.00")` bằng nhau về số học nhưng hash vẫn gọi `BigDecimal.hashCode()` gốc, sẽ vi phạm hợp đồng vì `BigDecimal.equals` phân biệt scale.

### Hợp đồng `toString()`

`toString` chủ yếu phục vụ quan sát và chẩn đoán. Không nên tự động đưa tất cả trường vào chuỗi log: password, token, khóa bí mật, thông tin riêng tư, object graph có vòng tham chiếu và quan hệ ORM tải lười đều cần xét riêng. Không nên viết logic nghiệp vụ dựa vào định dạng `toString` vì đó không phải serialization ổn định.

### Sự ổn định khi làm khóa

Các class `HashMap` và `HashSet` dùng `hashCode` để chọn vùng tìm kiếm rồi dùng `equals` để xác định phần tử/khóa. Một object có thể hợp đồng `equals/hashCode` hợp lệ tại mỗi thời điểm nhưng **không thích hợp làm khóa** nếu trường tham gia hash bị sửa sau khi chèn.

## 3. Bảng rà soát mã IDE tạo

| Câu hỏi khi review | Dấu hiệu cần chú ý | Cách xử lý |
| --- | --- | --- |
| Những trường nào quyết định bằng nhau? | IDE tích chọn tất cả, gồm timestamp, cache, token hoặc trạng thái tạm | Viết trước định nghĩa bằng nhau; chỉ dùng những trường thuộc hợp đồng |
| So sánh reference hay value? | `==` ở trường `String` / object | Dùng `Objects.equals` hoặc `equals` theo miền; `==` phù hợp với primitive và enum |
| Có override cả hai phương thức không? | Chỉ có `equals` hoặc hash dùng bộ trường khác | Đối chiếu `equals/hashCode` cùng một lần review |
| Có trường mutable không? | `List`, array hoặc setter sửa khóa sau khi đưa vào `HashMap` | Dùng dữ liệu khóa ổn định; sao chép phòng vệ mutable input/output |
| Array được so sánh thế nào? | `Objects.equals(a, b)` hoặc `Objects.hash(array)` | `Arrays.equals/hashCode` với mảng 1 chiều, `Arrays.deepEquals/deepHashCode` khi cần so nested arrays |
| `BigDecimal` có cùng tiêu chí ở equals/hash? | So số bằng `compareTo`, hash lại theo scale gốc | Xác định liệu scale có thuộc giá trị; chuẩn hóa cả equals và hash nếu không |
| Kế thừa có ảnh hưởng không? | `getClass()`, `instanceof` và `super.equals()` được chọn máy móc | Xét đối xứng/bắc cầu, phân cấp class và hợp đồng của superclass |
| Null và kiểu trường đặc biệt? | Gọi `field.equals(...)` khi `field` nullable; float/double so không chủ đích | Dùng so sánh null-safe; xác định quy tắc cho NaN, +0.0/-0.0 và precision |
| `toString` có an toàn không? | In secret, toàn bộ graph hoặc dữ liệu tải lười | Chỉ in trường phục vụ chẩn đoán và được phép hiển thị |
| Có thay đổi contract khi sửa class? | Bổ sung trường rồi bấm “Regenerate all” | Review diff, kiểm tra hành vi collections và compatibility trước khi chấp nhận |

Bảng là bộ câu hỏi review, không phải checklist buộc mọi class phải override cả ba phương thức: class dùng danh tính mặc định của `Object` có thể chủ ý giữ mặc định.

## 4. Ví dụ Java 17: bản hợp đồng có chủ đích

Giả sử `CustomerKey` dùng mã quốc gia, mã khách và mảng cấp quyền để xác định một **khóa logic**. Trường `token` là dữ liệu nhạy cảm, không góp phần vào quan hệ bằng nhau và không được lộ qua `toString`. Mảng đầu vào có thể bị bên gọi sửa; constructor phải tự sao chép.

Lưu **toàn bộ** ví dụ sau thành `ContractReviewDemo.java`:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ContractReviewDemo {
    static final class CustomerKey {
        private final String country;
        private final String customerId;
        private final int[] scopes;
        private final String token;

        CustomerKey(String country, String customerId, int[] scopes, String token) {
            this.country = Objects.requireNonNull(country, "country");
            this.customerId = Objects.requireNonNull(customerId, "customerId");
            this.scopes = Objects.requireNonNull(scopes, "scopes").clone();
            this.token = Objects.requireNonNull(token, "token");
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof CustomerKey other)) return false;
            return country.equals(other.country)
                    && customerId.equals(other.customerId)
                    && Arrays.equals(scopes, other.scopes);
        }

        @Override
        public int hashCode() {
            int result = Objects.hash(country, customerId);
            return 31 * result + Arrays.hashCode(scopes);
        }

        @Override
        public String toString() {
            return "CustomerKey[country=" + country
                    + ", customerId=" + customerId
                    + ", scopes=" + Arrays.toString(scopes) + "]";
        }
    }

    public static void main(String[] args) {
        int[] input = {1, 2};
        CustomerKey a = new CustomerKey("VN", "C-7", input, "token-secret");
        CustomerKey b = new CustomerKey("VN", "C-7", new int[] {1, 2}, "other-token");

        System.out.println("Equal value: " + a.equals(b));
        System.out.println("Equal hashes: " + (a.hashCode() == b.hashCode()));

        input[0] = 99; // Chỉ sửa mảng của bên gọi.
        System.out.println("Stable after input change: " + a.equals(b));

        Set<CustomerKey> keys = new HashSet<>();
        keys.add(a);
        keys.add(b);
        System.out.println("Distinct logical keys: " + keys.size());
        System.out.println("Find equal key: " + keys.contains(b));
        System.out.println("Token hidden: " + !a.toString().contains("token-secret"));
        System.out.println("Not equal to null: " + !a.equals(null));
    }
}
```

Biên dịch và chạy với **JDK 17+**:

```bash
javac ContractReviewDemo.java
java ContractReviewDemo
```

Kết quả chuẩn:

```text
Equal value: true
Equal hashes: true
Stable after input change: true
Distinct logical keys: 1
Find equal key: true
Token hidden: true
Not equal to null: true
```

Các quyết định cần review trong mã:

- `CustomerKey` là `final`, nên phép kiểm `instanceof CustomerKey other` không phải xử lý chuyện subclass bổ sung trạng thái bằng nhau.
- `country`, `customerId` và nội dung `scopes` là toàn bộ quan hệ bằng nhau; `token` cố ý không tham gia. Nếu nghiệp vụ thực tế đòi hỏi token phân biệt khóa, phải sửa định nghĩa hợp đồng trước.
- `Arrays.equals(scopes, other.scopes)` so các phần tử của mảng `int[]`; `Objects.equals(scopes, other.scopes)` sẽ dựa vào `equals` của chính đối tượng mảng, tức kiểm tra cùng mảng.
- `hashCode` dùng cùng bộ trường với `equals`, trong đó mảng được băm theo nội dung bằng `Arrays.hashCode`.
- `scopes.clone()` ngăn bên gọi sửa trạng thái nội bộ sau khi tạo khóa. Vì ví dụ không cung cấp getter xuất mảng nên không có đường sửa ngược; nếu bổ sung getter thì cũng phải trả về bản sao.
- `toString` in dữ liệu có ích nhưng không in token. Trong hệ thống thật, ngay cả `customerId` hoặc scopes cũng có thể cần ẩn/bỏ bớt tùy phân loại dữ liệu.

**Không nên máy móc áp dụng mẫu này cho entity ORM:** logic này phù hợp với kiểu khóa giá trị bất biến do ví dụ xác định. Với entity có vòng đời riêng, lazy field, proxy hay ID được cấp muộn, cần thiết kế một hợp đồng khác.

## 5. Phản ví dụ: ba lỗi dễ xuất hiện trong kết quả Generate

### 5.1. Mảng tưởng là đã so theo nội dung

IDE có thể sinh phiên bản không như bạn mong muốn, tùy cách chọn mẫu và tùy phiên bản:

```java
// Ví dụ không đúng nếu yêu cầu mảng được so theo PHẦN TỬ.
return Objects.equals(this.scopes, other.scopes);

// Và cách băm tương ứng theo danh tính mảng, không theo nội dung.
return Objects.hash((Object) scopes);
```

Hai mảng `new int[] {1, 2}` khác tham chiếu dù có cùng phần tử. Thay bằng `Arrays.equals(scopes, other.scopes)` và `Arrays.hashCode(scopes)`. Với mảng nhiều chiều, xác định xem cần so từng mảng con theo nội dung hay nhận diện từng tham chiếu; nếu cần nội dung lồng nhau, cân nhắc `Arrays.deepEquals` và `Arrays.deepHashCode`.

Đừng sửa mỗi `equals` mà quên `hashCode`. Một cặp phương thức có thể tạo mã băm nhất quán theo **danh tính mảng**, nhưng vẫn không đạt hợp đồng nghiệp vụ **giá trị mảng**.

### 5.2. Trường mutable phá khả năng tìm khóa

```java
// Minh họa rủi ro, không phải mẫu khóa nên sử dụng.
class MutableKey {
    String code;
    MutableKey(String code) { this.code = code; }
    @Override public boolean equals(Object o) {
        return o instanceof MutableKey other
                && Objects.equals(code, other.code);
    }
    @Override public int hashCode() {
        return Objects.hashCode(code);
    }
}
```

Nếu thêm `MutableKey("A")` vào `HashSet` rồi gán `key.code = "B"`, hash của khóa thay đổi trong khi vị trí lưu ở bảng băm không được tổ chức lại. Sau đó, `contains(key)` hoặc `remove(key)` **có thể** không tìm được khóa. Không khẳng định lỗi xảy ra trong mọi kích thước bảng và mọi tổ hợp hash; điều phải bảo đảm là **không thay đổi các trường dùng cho hash khi object đang làm khóa**.

Các cách xử lý: dùng khóa bất biến; dùng ID ổn định; hoặc xóa khỏi collection trước khi thay đổi rồi thêm lại theo quy trình được kiểm soát (nếu thiết kế collection cho phép). Việc trường được khai báo `final` chưa đủ nếu nó tham chiếu đến `List` hay mảng có thể bị sửa.

### 5.3. Thêm mọi trường vào `toString`

Một kết quả kiểu:

```java
return "Account{email='" + email
        + "', password='" + password
        + "', accessToken='" + accessToken + "'}";
```

có thể làm lộ thông tin qua log ứng dụng, exception message và công cụ quan sát. Review các trường nhạy cảm, mảng byte chứa khóa, quan hệ vòng và các collection lớn trước khi merge. Dùng danh sách trường cho phép in; đừng trông chờ người gọi luôn tránh log `toString()`.

## 6. Kế thừa, superclass và chiến lược so sánh kiểu

IDE thường hỏi: dùng `getClass()` hay `instanceof`? Gọi `super.equals()` không? Không có một lựa chọn đúng cho mọi mô hình.

- `getClass() == obj.getClass()` yêu cầu **đúng cùng runtime class**. Điều này thường hợp lý nếu equality chỉ định nghĩa trong một lớp cụ thể, nhưng có thể xung đột với proxy do framework tạo hoặc yêu cầu so sánh đa hình.
- `obj instanceof Base` chấp nhận subclass. Nếu subclass thêm trường vào `equals`, dễ có `base.equals(sub) == true` nhưng `sub.equals(base) == false`. Một cách “sửa nhanh” có thể làm hỏng tính bắc cầu.
- `super.equals(obj)` chỉ đúng nếu superclass đã có hợp đồng bằng nhau tương thích; nếu superclass chỉ dùng `Object.equals`, gọi nó có thể khiến mọi instance khác tham chiếu đều không bằng nhau, dù trường của subclass trùng nhau.
- Class value object không cần kế thừa thường nên được thiết kế `final` để giới hạn rủi ro equality theo phân cấp. Nếu cần kế thừa thực sự, quyết định cách biểu diễn equality ngay trong mô hình loại, đồng thời viết kiểm thử đối xứng/bắc cầu giữa cả các kiểu.

Một số IDE hoặc thư viện còn cho tùy chọn “include superclass fields”, “call super”, “use getters”. Getter bị override, có side effect hoặc lazy-loading có thể khiến `equals/hashCode/toString` gọi hành vi ngoài dự tính. Cần hiểu lựa chọn được tick làm thay đổi điều gì.

## 7. Lưu ý với record, Lombok và `BigDecimal`

### Record vẫn cần review hợp đồng

Với Java 17, `record` tự sinh constructor chuẩn, accessor, `equals`, `hashCode` và `toString` từ các component. Điều này giảm mã lặp, nhưng **không tự giải quyết các quyết định nghiệp vụ**:

```java
record ImageKey(byte[] digest) { }
```

Hai mảng `byte[]` có cùng bytes nhưng là hai đối tượng khác nhau không được record mặc định so bằng nhau theo nội dung mảng. Record cũng không tự sao chép `digest` hoặc ngăn sửa qua accessor. Nếu component là token/mật khẩu, `toString` tự sinh có thể đưa giá trị nhạy cảm vào chuỗi. Cân nhắc mô hình component bất biến thích hợp hoặc override có chủ đích, giữ ba hợp đồng nhất quán.

### Lombok sinh mã ở lúc biên dịch

Các annotation như `@EqualsAndHashCode` và `@ToString` (Lombok) cũng cần review tương đương mã IDE tạo. Kiểm tra `onlyExplicitlyIncluded` / `@Include` / `@Exclude`, `callSuper`, getter vs field, và dữ liệu mật. Tự động sinh mã không khiến quyết định chọn trường trở nên đúng; phải kiểm thử hành vi thực tế sau biên dịch.

### `BigDecimal`: giá trị số hay giá trị cả scale?

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.equals(b));       // false
System.out.println(a.compareTo(b) == 0); // true
```

Nếu domain coi **scale** là một phần của giá trị, dùng nhất quán `BigDecimal.equals/hashCode` có thể là đúng. Nếu domain chỉ quan tâm độ lớn số học, bạn phải định nghĩa biểu diễn chuẩn trước khi so và băm, rồi áp dụng nhất quán cho cả hai; `stripTrailingZeros()` là một công cụ có thể dùng với hiểu biết đầy đủ về hành vi trả về của nó. Không sửa riêng so sánh `equals` sang `compareTo == 0` khi `hashCode` vẫn do IDE sinh theo raw `BigDecimal`.

### Floating point và collection

Với `double`/`float`, `==`, `Double.compare` và `Double.equals` khác nhau ở một số ca như NaN và signed zero. Nếu IDE sinh so sánh `Double.compare(...) == 0`, cần xác định điều đó có đúng với miền nghiệp vụ không. Với giá trị đo có sai số, biểu thức “bằng nhau nếu |a-b| < epsilon” thường **không bắc cầu**, nên không thể tùy tiện dùng làm `equals` và khóa hash. Cân nhắc lượng tử hóa/chuẩn hóa từ trước hoặc một phép so gần đúng riêng không phải `equals`.

## 8. Quy trình review sau khi Generate

1. **Viết một câu định nghĩa equality.** Chỉ rõ lớp này so theo giá trị, ID thực thể hay danh tính tham chiếu; xác định quy tắc về `null` và kiểu runtime.
2. **Đọc từng nhánh của `equals`.** Kiểm tra lớp đối tượng, superclass, danh sách trường, array, cách so object, thứ tự/ý nghĩa collection, chuẩn hóa và quy tắc số đặc biệt.
3. **So lại `hashCode` ngay bên cạnh.** Tất cả quyết định làm hai object “bằng nhau” phải cho cùng hash; xem trường mutable và cách xử lý array, `BigDecimal`, nested data.
4. **Kiểm tra `toString`.** Bỏ hoặc ẩn thông tin nhạy cảm; tránh đi qua object graph sâu, collection rất lớn, lazy property hoặc phép tính có side effect.
5. **Xem constructor/getter/setter được sinh.** Chỉ `final` cho tham chiếu chưa đủ: cần copy phòng vệ nếu giữ dữ liệu mutable. Setter làm đổi khóa có thể phá cách dùng trong collection.
6. **Chạy các kiểm thử hợp đồng và tình huống thực tế.** Dùng hai instance độc lập nhưng có cùng giá trị, đối tượng khác giá trị, `null`, subclass nếu có, collection `HashSet/HashMap`, tình huống thay đổi dữ liệu, log có bí mật.
7. **Review diff khi sinh lại.** Sau khi thêm/đổi tên trường, IDE có thể đưa trường mới vào so sánh hoặc log. Đó là thay đổi hành vi có thể ảnh hưởng serialization, cache, collection và các caller khác.

**Kiểm thử tối thiểu nên có** (viết theo từng class, không chỉ copy nguyên xi):

- `x.equals(x)`; `!x.equals(null)`; hai thể hiện cùng giá trị được tạo độc lập; hai giá trị khác nhau.
- `x.equals(y) == y.equals(x)`, kiểm tra bộ ba `x, y, z` khi có logic phức tạp hoặc kế thừa.
- Nếu `x.equals(y)` thì `x.hashCode() == y.hashCode()`.
- Thêm `x` vào `HashSet`; tìm bằng `y` cùng giá trị. Nếu dùng `HashMap`, truy vấn bằng khóa tương đương.
- Thử sửa input, collection hoặc mảng được truyền vào/nhận từ getter để chắc giá trị khóa không bị thay đổi ngoài ý muốn.
- `toString()` không chứa bí mật và không kích hoạt hành vi ngoài dự định.

**Không kiểm thử bằng cách đòi hash khác nhau đối với hai giá trị khác nhau:** va chạm hash hợp lệ. Cũng không so với một giá trị hash cố định do một lần IDE sinh ra nếu không có cam kết thuật toán hash là một phần của API.

## 9. Hai câu hỏi review để chặn lỗi phổ biến

**Tình huống A:** Sau khi thêm trường `updatedAt`, IDE gợi ý sinh lại `equals/hashCode` và tự chọn cả trường mới. Chỉ chấp nhận nếu thời điểm cập nhật thật sự là một phần định nghĩa bằng nhau. Nếu đó là metadata thay đổi thường xuyên, đưa vào equality có thể khiến object cùng thực thể bị xem là khác, hoặc làm mất khả năng tìm trong `HashMap`.

**Tình huống B:** IDE sinh `toString` có `orders` và `customer` trong một quan hệ hai chiều. Việc in log có thể duyệt vòng tham chiếu, phát sinh nhiều truy vấn lazy-loading hoặc lộ dữ liệu lớn. Hãy giới hạn `toString` vào vài trường chẩn đoán an toàn (ví dụ một ID đã được phép log), không in toàn bộ đồ thị.

**Quy tắc quyết định:** Sinh mã giúp tiết kiệm thao tác gõ. Người review phải kiểm chứng rằng phép bằng nhau mô tả đúng miền nghiệp vụ, hash luôn tương thích, trạng thái của khóa không thay đổi ngoài ý muốn và chuỗi debug an toàn. Code “Generate…” là điểm bắt đầu để kiểm tra, không phải bằng chứng rằng hợp đồng đã đúng.

## Tài liệu tham khảo

- [Java SE 17 — Object.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)): năm tính chất của quan hệ bằng nhau.
- [Java SE 17 — Object.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#hashCode()): quan hệ bắt buộc giữa `equals` và hash.
- [Java SE 17 — Arrays](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): `equals`, `hashCode` và các biến thể deep.
- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): phân biệt `equals` với `compareTo`.
- [Java SE 17 — Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): hợp đồng phương thức mặc định cho record.
