# Cài đặt `equals()` bằng nhiều trường theo định nghĩa bằng nhau đã chọn

## 1. Trọng tâm: chọn đúng các trường trước khi viết code

Khi cài đặt `equals(Object)` cho một lớp Java, câu hỏi đầu tiên **không phải** “lớp này có bao nhiêu trường?” mà là: **“Theo quy tắc của miền bài toán, khi nào hai instance được coi là bằng nhau?”** Từ câu trả lời đó mới xác định tập trường cần kết hợp trong phép so sánh.

Một đối tượng có thể chứa nhiều loại dữ liệu:

- **Trường định danh:** tạo thành khóa nhận diện thực thể (ví dụ `tenantId` và `memberNumber` kết hợp).
- **Trường giá trị cốt lõi:** xác định giá trị của value object (ví dụ `currency` và `amount` của một số tiền).
- **Trường mô tả hoặc trạng thái:** tên hiển thị, thời điểm cập nhật, trạng thái xử lý, số lần đăng nhập; chúng có thể không thuộc định nghĩa bằng nhau.
- **Trường tính toán/phụ trợ:** cache, bộ đếm, logger, dữ liệu suy ra; thông thường không tham gia equality nếu không mang ý nghĩa so sánh.

**Không có quy tắc luôn đưa mọi field vào `equals()`.** Với *value object*, thường so sánh mọi thành phần có ý nghĩa; với *entity*, thường so sánh danh tính ổn định, có thể là một trường hoặc một tổ hợp trường. Hai object có cùng tên hoặc cùng trạng thái chưa chắc là cùng thực thể; hai bản thể hiện cùng ID có thể khác trạng thái.

Ví dụ: trong hệ thống nhiều khách hàng doanh nghiệp, mã hội viên `"M-17"` chỉ duy nhất **trong từng tenant**. Nếu doanh nghiệp còn quy định cùng mã có thể xuất hiện ở nhiều khu vực và khu vực là một phần của danh tính không đổi, khóa nhận diện phải gồm **`(tenantId, memberNumber, region)`**. Chỉ so sánh `memberNumber` sẽ gộp nhầm các hội viên không tương đương. Nếu trong một thiết kế khác `region` chỉ là nơi cư trú thay đổi được, trường này *không được* đưa vào khóa equality; phải dùng định nghĩa của miền đó.

## 2. Hợp đồng của `equals()` và `hashCode()`

Lớp `Object` định nghĩa `equals(Object)`. Triển khai mặc định kiểm tra tham chiếu cùng đối tượng; override cho phép thay bằng bình đẳng có ý nghĩa với ứng dụng. Dù so một hay nhiều trường, `equals()` phải thỏa:

| Tính chất | Yêu cầu |
| --- | --- |
| Phản xạ (reflexive) | Với đối tượng `x` khác `null`, `x.equals(x)` là `true` |
| Đối xứng (symmetric) | `x.equals(y)` và `y.equals(x)` phải cùng kết quả |
| Bắc cầu (transitive) | Nếu `x.equals(y)` và `y.equals(z)` đều `true`, thì `x.equals(z)` phải `true` |
| Nhất quán (consistent) | Khi các dữ liệu dùng để so sánh không đổi, các lần gọi liên tiếp cho cùng kết quả |
| So với `null` | `x.equals(null)` luôn là `false` nếu `x` khác `null` |

Quy tắc bắt buộc của `hashCode()`: **nếu `x.equals(y) == true` thì `x.hashCode() == y.hashCode()`**. Hai hash bằng nhau không kéo theo hai object bằng nhau vì có thể xảy ra va chạm.

Hệ quả khi chọn nhiều trường: nếu `equals()` dùng `a`, `b`, `c`, thì `hashCode()` cũng phải dựa vào đúng các thành phần xác định equality đó với cách xử lý giá trị nhất quán. Nếu `equals()` bỏ qua `displayName` thì `hashCode()` không được đưa `displayName` vào. Không được dùng `System.identityHashCode()` làm hash cho object equality theo giá trị.

## 3. Công thức kết hợp nhiều trường một cách an toàn

Một mẫu triển khai thông thường cho lớp `final` có các trường reference:

```java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (!(other instanceof Example that)) return false;

    return Objects.equals(fieldA, that.fieldA)
        && Objects.equals(fieldB, that.fieldB)
        && Objects.equals(fieldC, that.fieldC);
}

@Override
public int hashCode() {
    return Objects.hash(fieldA, fieldB, fieldC);
}
```

Đây là **mảnh code minh họa**, cần đặt trong class `Example` thực tế và import `java.util.Objects`. Điều kiện `instanceof Example that` dùng pattern matching có từ Java 16; Java 17 chạy được.

Vai trò của từng phần:

1. `this == other` là tối ưu hóa đúng: cùng một instance luôn bằng chính nó.
2. Kiểm tra kiểu loại bỏ `null` và đối tượng không thuộc kiểu phù hợp; với một lớp `final`, không phát sinh lớp con để phá quy tắc so sánh.
3. Toán tử `&&` đòi hỏi **tất cả** các thành phần được chọn cùng thỏa phép so sánh. Nếu chỉ một trường khác nhau, hai đối tượng không bằng nhau.
4. `Objects.equals(a, b)` xử lý `null` an toàn: cùng `null` thì `true`; một `null` thì `false`; hai giá trị khác `null` thì dùng `a.equals(b)`.
5. `Objects.hash(a, b, c)` tổng hợp hash nhiều trường theo thứ tự. Lời gọi với cùng bộ giá trị có hash nhất quán; sự khác thứ tự có thể đổi hash, nên phải giữ thứ tự ổn định trong code.

**Chọn phép so sánh theo kiểu trường:** `==` cho primitive `int`/`boolean`; `Objects.equals` hoặc `.equals` cho reference có ngữ nghĩa giá trị; `Arrays.equals`/`Arrays.deepEquals` cho mảng tùy cấu trúc. Không nên dùng `==` để so hai chuỗi hoặc wrapper object khi mục tiêu là nội dung. Với `double` và `float`, cân nhắc `Double.compare`/`Float.compare` cùng hàm hash tương ứng để xử lý NaN và số 0 có dấu một cách nhất quán.

## 4. Ví dụ đầy đủ Java 17: khóa hội viên gồm ba trường

Ta giả định quy tắc nghiệp vụ sau:

- Một hội viên được nhận diện bởi **cặp tenant + mã hội viên + khu vực**. Trong ví dụ này cả ba là các thành phần định danh ổn định; `region` được phép `null` và `null` là một giá trị phân biệt hợp lệ trong mô hình minh họa.
- `displayName` chỉ là thuộc tính hiển thị, có thể đổi, **không** tham gia equality.
- Mỗi phần định danh được so sánh đúng nguyên văn, có phân biệt chữ hoa/chữ thường; trường hợp cần không phân biệt phải có quy tắc chuẩn hóa dữ liệu riêng, đồng nhất ở mọi nơi.

Lưu vào tệp **`MultiFieldEqualsDemo.java`**:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class MultiFieldEqualsDemo {
    static final class Membership {
        private final String tenantId;
        private final String memberNumber;
        private final String region; // Cho phép null trong ví dụ
        private String displayName;  // Có thể thay đổi, không tham gia equals

        Membership(String tenantId, String memberNumber,
                   String region, String displayName) {
            this.tenantId = Objects.requireNonNull(tenantId, "tenantId");
            this.memberNumber = Objects.requireNonNull(memberNumber, "memberNumber");
            this.region = region;
            this.displayName = displayName;
        }

        void setDisplayName(String newDisplayName) {
            this.displayName = newDisplayName;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Membership that)) {
                return false;
            }
            return tenantId.equals(that.tenantId)
                && memberNumber.equals(that.memberNumber)
                && Objects.equals(region, that.region);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenantId, memberNumber, region);
        }
    }

    record Coordinate(int x, int y) {}

    public static void main(String[] args) {
        Membership a = new Membership("ACME", "M-17", "VN", "An");
        Membership b = new Membership("ACME", "M-17", "VN", "Nguyen An");
        Membership c = new Membership("ACME", "M-17", "SG", "An");
        Membership d = new Membership("BETA", "M-17", "VN", "An");
        Membership e = new Membership("ACME", "M-17", null, "An");
        Membership f = new Membership("ACME", "M-17", null, "Khac");

        System.out.println("a == b: " + (a == b));
        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("a.equals(c): " + a.equals(c));
        System.out.println("a.equals(d): " + a.equals(d));
        System.out.println("e.equals(f): " + e.equals(f));
        System.out.println("a.equals(null): " + a.equals(null));
        System.out.println("hash(a) == hash(b): " + (a.hashCode() == b.hashCode()));

        Set<Membership> members = new HashSet<>();
        members.add(a);
        members.add(b);
        members.add(c);
        members.add(d);
        members.add(e);
        members.add(f);
        System.out.println("HashSet size: " + members.size());

        a.setDisplayName("An moi");
        System.out.println("Contains a after rename: " + members.contains(a));
        System.out.println("Contains same identity: " + members.contains(
            new Membership("ACME", "M-17", "VN", "Ten khac")));

        Coordinate p = new Coordinate(2, 5);
        Coordinate q = new Coordinate(2, 5);
        Coordinate r = new Coordinate(2, 6);
        System.out.println("record p.equals(q): " + p.equals(q));
        System.out.println("record p.equals(r): " + p.equals(r));
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên** trong thư mục có tệp:

```bash
javac MultiFieldEqualsDemo.java
java MultiFieldEqualsDemo
```

Kết quả chuẩn:

```text
a == b: false
a.equals(b): true
a.equals(c): false
a.equals(d): false
e.equals(f): true
a.equals(null): false
hash(a) == hash(b): true
HashSet size: 4
Contains a after rename: true
Contains same identity: true
record p.equals(q): true
record p.equals(r): false
```

**Phân tích kết quả:**

- `a` và `b` là **hai instance** nên `a == b` là `false`; nhưng ba thành phần định danh đều giống nhau nên `a.equals(b)` là `true`, dù tên hiển thị khác.
- `c` chỉ khác `region` và `d` chỉ khác `tenantId`, vẫn phải là hai thực thể khác `a`. Đây chính là lý do cần kết hợp đủ các trường theo định nghĩa đã chọn.
- `e` và `f` có cùng `region == null`; `Objects.equals(null, null)` cho `true`. `region == null` **không** đồng nghĩa với `"VN"`. Trong nghiệp vụ thật, cần xác định `null` có thực sự là giá trị định danh hợp lệ hay phải từ chối ngay khi khởi tạo.
- `HashSet` chỉ có bốn khóa phân biệt theo equality: nhóm `(ACME, M-17, VN)`, `(ACME, M-17, SG)`, `(BETA, M-17, VN)` và `(ACME, M-17, null)`. `b` trùng `a`; `f` trùng `e`.
- Đổi `displayName` của `a` không ảnh hưởng `hashCode()` vì thuộc tính đó không tham gia equality. Vì vậy `contains(a)` vẫn đúng; một instance mới cùng ba thành phần định danh cũng được nhận diện đã tồn tại.
- `record Coordinate` tự sinh `equals()` và `hashCode()` dựa trên các component `x`, `y`. Đây là lựa chọn gọn cho value object khi định nghĩa bằng nhau chính là toàn bộ thành phần record. Record không tự hiểu quy tắc định danh nghiệp vụ: muốn bỏ qua component, cần tự thiết kế lại.

## 5. Quy trình chọn và kết hợp nhiều trường

### Bước 1 — Viết định nghĩa bằng nhau bằng lời

Ví dụ: “Hai `Membership` bằng nhau khi và chỉ khi cùng `tenantId`, `memberNumber` và `region`”. Hãy ghi rõ miền giá trị, ý nghĩa `null`, quy tắc phân biệt chữ hoa/chữ thường và liệu đối tượng chưa được cấp ID có thể được so sánh bằng ID hay không.

Một bảng quyết định đơn giản:

| Trường | Có thuộc equality? | Lý do |
| --- | --- | --- |
| `tenantId` | Có | Mã hội viên chỉ duy nhất trong phạm vi tenant |
| `memberNumber` | Có | Mã được cấp để nhận diện hội viên |
| `region` | Có, **theo giả định của ví dụ** | Khu vực là thành phần cố định của namespace định danh |
| `displayName` | Không | Chỉ mô tả; có thể đổi mà không đổi thực thể |

**Không sao chép bảng này sang domain khác** khi chưa xác định đúng bất biến nghiệp vụ của domain đó.

### Bước 2 — Giữ các thành phần equality ổn định

Trong ví dụ, ba thành phần định danh được khai báo `final`. `final` giữ tham chiếu của field không bị gán lại, nhưng **không làm cho object được tham chiếu trở nên bất biến**. Với thành phần là `List`, `Set`, mảng hoặc object có thể thay đổi, cần dùng bản sao phòng vệ và thiết kế phần tử bất biến nếu muốn sử dụng nó trong equality/hash ổn định.

### Bước 3 — So từng trường theo đúng kiểu

- Primitive `int`, `long`, `boolean`: thường dùng `==` (với số thực xem thêm chú ý về NaN và số 0 có dấu).
- `String` và value object bất biến: `Objects.equals(a, b)` (an toàn khi có `null`) hoặc `a.equals(b)` khi chắc chắn không `null`.
- `List`: `List.equals` so thứ tự và giá trị phần tử theo quy tắc của từng phần tử.
- `Set`: `Set.equals` so các phần tử của tập, không dựa trên thứ tự duyệt.
- `Map`: `Map.equals` so các ánh xạ key-value.
- Mảng: dùng `Arrays.equals` hoặc `Arrays.deepEquals` theo cấp lồng nhau; `Objects.equals` với hai mảng thông thường chỉ kiểm tra **cùng mảng tham chiếu**, không so nội dung.
- Loại có so sánh đặc thù như tiền tệ/số thập phân: cần xác định rõ canonical form trước khi chọn phương thức so sánh.

### Bước 4 — Cài `hashCode()` theo cùng định nghĩa

Nếu đã chọn tổ hợp `(tenantId, memberNumber, region)` trong `equals()`, chỉ dùng bộ này để tính hash. Với lớp có ít trường, `Objects.hash(...)` dễ đọc và giảm lỗi bỏ sót. Nếu hiệu năng đo được yêu cầu tối ưu, có thể tổng hợp bằng `31 * result + fieldHash`, nhưng phải đảm bảo cách so sánh và cách hash tương thích.

Lưu ý **thứ tự**: `Objects.hash(a, b)` và `Objects.hash(b, a)` có thể khác nhau; việc hash không thay cho phép so sánh. Đừng dựa vào hash để phân biệt duy nhất các object.

### Bước 5 — Tạo trường hợp thử phân biệt từng thành phần

Đối với định nghĩa bằng nhau có ba trường, kiểm tra ít nhất:

1. Cùng tham chiếu; hai instance khác nhau nhưng cả ba trường bằng nhau.
2. Chỉ **một trường** trong ba khác nhau, lặp lại cho từng trường.
3. Cả hai cùng `null` ở trường cho phép `null`; một bên `null`, một bên có giá trị.
4. Trường ngoài định nghĩa (`displayName`) khác nhau nhưng vẫn phải bằng nhau.
5. Hai object bằng nhau phải có cùng hash; `HashSet`/`HashMap` nhìn nhận khóa nhất quán.
6. Gọi `equals(null)` và `equals` với object kiểu khác; kiểm tra phản xạ, đối xứng, bắc cầu.

Kiểm thử chỉ với “mọi field giống nhau” không đủ: nó có thể che lỗi quên một trường hoặc đưa nhầm một trường mô tả vào equality.

## 6. Những tình huống cần xử lý riêng

### 6.1. Trường hợp có mảng

Hai mảng riêng biệt chứa cùng phần tử vẫn thường trả về `false` khi gọi trực tiếp `array1.equals(array2)`. Nếu mảng là thành phần của equality, dùng cặp hàm đồng bộ:

```java
// Minh họa bên trong một class có int[] scores:
return Arrays.equals(this.scores, that.scores);
```

```java
// Phần tương ứng trong hashCode():
return Arrays.hashCode(scores);
```

Cả hai mảnh cần `import java.util.Arrays;`, kiểu `that` phù hợp và cùng các thành phần khác của class nếu có. Với mảng nhiều chiều chứa các mảng con, thường dùng `Arrays.deepEquals(...)` kết hợp `Arrays.deepHashCode(...)`. Lưu ý các mảng có thể bị sửa; cần bản sao phòng vệ khi chúng ảnh hưởng đến hash hoặc thành phần của một record.

### 6.2. `BigDecimal`: cùng trị số chưa chắc bằng theo `equals()`

`new BigDecimal("1.0").equals(new BigDecimal("1.00"))` là `false` vì khác `scale`, dù `compareTo(...) == 0`. Nếu định nghĩa bằng nhau của value object là **bằng chính xác theo `BigDecimal.equals`**, dùng `Objects.equals` và `BigDecimal.hashCode` cùng nhất quán. Nếu nghiệp vụ muốn coi `1.0` và `1.00` là cùng giá trị, cần một cách chuẩn hóa thống nhất và định nghĩa hash theo giá trị đã chuẩn hóa, không chỉ đổi mỗi phép so sánh thành `compareTo(...) == 0` rồi giữ nguyên `BigDecimal.hashCode()`. Với tiền, cần xác định cả đơn vị tiền tệ và quy tắc scale/làm tròn.

### 6.3. Chuỗi có chuẩn hóa

Mã `"ab-01"` và `"AB-01"` có bằng nhau không phụ thuộc chính sách nghiệp vụ. Nếu muốn không phân biệt hoa/thường, ưu tiên **chuẩn hóa ID khi nhận/tạo đối tượng** rồi lưu một dạng chuẩn ổn định, thay vì so `equalsIgnoreCase` nhưng `hashCode` lại dùng `String.hashCode` của chuỗi gốc. Nếu chuẩn hóa có phụ thuộc ngôn ngữ, tránh gọi `toLowerCase()` mà không xác định locale (ví dụ dùng `Locale.ROOT` cho mã kỹ thuật khi phù hợp). Không tự `trim`/bỏ dấu/phân tách ký tự nếu quy tắc miền không cho phép.

### 6.4. Kế thừa và tính đối xứng

Việc subclass thêm một trường vào `equals()` trong khi lớp cha chỉ so trường chung có thể phá tính đối xứng hoặc bắc cầu. Ví dụ, cha xem hai đối tượng bằng nhau theo mã, còn con đòi cả mã và loại phụ; `parent.equals(child)` và `child.equals(parent)` dễ khác nhau. Một hướng đơn giản là dùng class `final` cho value type/entity định nghĩa equality cố định. Trong hệ phân cấp mở, cần xác định chính sách kiểu nhất quán (chẳng hạn `getClass()` hoặc quy tắc `instanceof` phù hợp), cùng thiết kế ở tất cả lớp; không trộn tùy ý. ORM proxy có thể làm việc so lớp runtime phức tạp hơn, nên tuân thủ chiến lược equality được khuyến nghị cho framework cụ thể.

### 6.5. ID cấp sau khi lưu và object có trạng thái biến đổi

Nếu entity mới có `id == null`, đoạn `Objects.equals(this.id, that.id)` có thể làm **mọi entity chưa lưu** bằng nhau vì cả hai ID đều `null`. Nếu ID được gán sau khi object đã được thêm vào `HashSet`, `hashCode()` đổi theo ID có thể làm `contains` hoặc `remove` thất bại. Cần chiến lược rõ cho thực thể transient/persisted, đảm bảo hash ổn định khi cần, hoặc cấp ID ổn định sớm. Đừng “sửa nhanh” bằng cách đưa tất cả các trường vào equality.

### 6.6. Record, Lombok và code tự sinh

- `record` trong Java tự sinh `equals/hashCode` dựa trên **tất cả** component, thích hợp khi đó chính là định nghĩa của value object. Với mảng, equality mặc định của component mảng không tự trở thành deep content equality.
- IDE và thư viện như Lombok có thể sinh `equals/hashCode`, nhưng **cần chọn đúng trường** (ví dụ include/exclude) theo quy tắc đã viết. Generated code đúng cú pháp vẫn có thể sai nghiệp vụ khi đưa thêm trường mutable/cache hoặc bỏ sót tenant ID.
- Khi thêm/xóa trường của class, luôn hỏi liệu định nghĩa equality có thay đổi hay không; không tự động cập nhật chỉ vì danh sách thuộc tính khác trước.

## 7. Những lỗi phổ biến và cách nhận biết

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Chỉ so `memberNumber`, quên `tenantId` | Trộn dữ liệu của hai tenant | Viết định nghĩa khóa ghép và thử từng trường khác nhau |
| Đưa `displayName` thay đổi được vào `equals/hashCode` | Cùng một entity có thể trở thành khác nhau sau đổi tên; khóa trong `HashSet` bị “mất” | Chỉ dùng các thành phần nhận diện ổn định |
| `equals()` dùng ba trường nhưng `hashCode()` dùng cả bốn | Các object `equals` có thể có hash khác; `HashMap/HashSet` hoạt động sai | Dùng cùng tập trường và cách chuẩn hóa |
| So reference bằng `==` khi muốn so nội dung | Hai instance có cùng giá trị bị coi khác nhau | `Objects.equals`/`equals` theo kiểu |
| So mảng bằng `Objects.equals` rồi kỳ vọng so phần tử | Hai mảng khác instance có cùng nội dung bị coi khác | `Arrays.equals/deepEquals` và hash tương ứng |
| Dùng `compareTo` cho `BigDecimal` nhưng giữ hash gốc | Vi phạm hợp đồng `equals/hashCode` | Chuẩn hóa giá trị và hash đồng nhất |
| So dữ liệu chưa chuẩn hóa ở một nơi, đã chuẩn hóa ở nơi khác | Equality không ổn định hoặc không nhất quán | Chuẩn hóa tại biên tạo dữ liệu |
| So class cha/con không có chính sách chung | Mất đối xứng hoặc bắc cầu | Thiết kế kế thừa và equality thống nhất; cân nhắc `final` |
| Chỉ so/hash theo ID còn `null` khi chưa lưu | Các entity mới bị gộp nhầm, hash đổi sau insert | Chiến lược riêng cho vòng đời identity |

## 8. Bài tập tự kiểm tra

**Bài 1.** Trong hệ thống nhiều tenant, mã phiếu `ticketNo` có thể lặp giữa các tenant. Nếu chỉ so `ticketNo`, cặp `(T1, A-10)` và `(T2, A-10)` có bằng nhau không theo nghiệp vụ?

**Đáp án:** Không, nếu namespace là từng tenant. `equals()` phải kết hợp `tenantId` và `ticketNo`; `hashCode()` theo cùng cặp.

**Bài 2.** Hai phiên bản của cùng `Membership` có cùng `tenantId`, `memberNumber`, `region` nhưng `displayName` khác. Theo định nghĩa trong ví dụ, `equals` trả gì?

**Đáp án:** `true`. Tên hiển thị không phải thành phần nhận diện hội viên.

**Bài 3.** Một developer cập nhật `equals()` để so thêm `region` nhưng quên sửa `hashCode()`, hiện hash chỉ dựa trên hai trường cũ. Có chắc luôn vi phạm hợp đồng không?

**Đáp án:** Chưa chắc: nếu hai object bằng nhau theo ba trường thì chúng cũng bằng nhau theo hai trường cũ, nên vẫn có cùng hash. Nhưng hash có thể phân phối kém hơn vì bỏ qua `region`, và code khó duy trì. Trường hợp **nguy hiểm vi phạm hợp đồng** là hash dùng các trường mà `equals()` bỏ qua (hoặc dùng một cách chuẩn hóa không nhất quán): hai object bằng nhau có thể sinh hash khác nhau. Dù hợp đồng chưa chắc bị phá, vẫn nên đồng bộ định nghĩa và mã hash cho dễ kiểm chứng.

**Bài 4.** `new BigDecimal("1.0")` và `new BigDecimal("1.00")` có cùng số trị trong toán học; `BigDecimal.equals` có coi bằng nhau không? Nếu dùng `compareTo==0` trong equality thì còn phải làm gì?

**Đáp án:** `BigDecimal.equals` trả `false`; muốn equality theo giá trị số học thì `hashCode` cũng phải tính từ biểu diễn chuẩn hóa tương ứng.

**Bài 5.** Hai `record Pair(int left, int right)` có `left` bằng nhau và `right` khác nhau. `record.equals` mặc định trả gì?

**Đáp án:** `false`, vì record mặc định so tất cả component của nó.

---

**Ghi nhớ:** Bước quan trọng nhất khi cài đặt `equals()` cho nhiều trường là **xác định trước tập trường nào tạo ra quan hệ bằng nhau theo miền nghiệp vụ**. Sau đó so từng trường bằng phép so sánh phù hợp, xử lý `null`/kiểu dữ liệu/kế thừa một cách nhất quán và xây dựng `hashCode()` tương thích. Tập trường dùng để nhận diện nên ổn định trong suốt thời gian object được dùng trong các cấu trúc băm.