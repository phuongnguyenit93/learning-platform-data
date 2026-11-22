# Kiểm thử `equals() == true` luôn kéo theo `hashCode()` bằng nhau trong Java

## 1. Điều cần chứng minh

Trong Java, hai đối tượng **khác `null`** mà `a.equals(b)` trả về `true` bắt buộc có cùng kết quả `hashCode()` tại thời điểm kiểm tra, khi các dữ liệu tham gia vào `equals()` và `hashCode()` không bị thay đổi:

~~~text
Nếu a.equals(b) == true thì a.hashCode() == b.hashCode().
~~~

Đây là hợp đồng của `java.lang.Object`. Nó quan trọng vì các cấu trúc dựa trên băm như `HashMap` và `HashSet` dùng hash code để xác định vị trí tìm kiếm rồi mới xét bình đẳng. Nếu đối tượng bằng nhau mà hash khác nhau, việc tra cứu bằng một đối tượng tương đương có thể thất bại.

**Chiều ngược lại không được đảm bảo:** cùng hash code **không có nghĩa** hai đối tượng bằng nhau. Va chạm băm (*hash collision*) là hợp lệ; hash code là số `int`, trong khi số lượng giá trị đối tượng có thể lớn hơn rất nhiều.

| Quan hệ quan sát | Kết luận về hợp đồng |
| --- | --- |
| `a.equals(b) == true` và hash của hai bên bằng nhau | Đạt điều kiện đang kiểm thử |
| `a.equals(b) == true` nhưng hash khác nhau | **Vi phạm** hợp đồng |
| `a.equals(b) == false` và hash bằng nhau | Hợp lệ; đây có thể là va chạm |
| `a.equals(b) == false` và hash khác nhau | Hợp lệ |
| `a == b` | Cùng đối tượng; hash hai lần phải ổn định nếu dữ liệu liên quan không đổi |

Chú ý: một cặp đối tượng vượt qua điều kiện này **chưa chứng minh toàn bộ `equals()` đúng**. `equals()` còn phải có tính phản xạ, đối xứng, bắc cầu và tính nhất quán; `x.equals(null)` phải là `false`. Một bộ kiểm thử tốt nên kiểm tra các tính chất đó, nhưng trọng tâm ở bài này là mệnh đề kéo theo từ `equals()` sang `hashCode()`.

## 2. Vì sao phải kiểm thử nhiều đối tượng bằng nhau nhưng khác tham chiếu?

Kiểm thử chỉ với `a.equals(a)` quá yếu: khi gọi `hashCode()` hai lần trên cùng đối tượng không thay đổi, kết quả vốn phải giống nhau. Cần tạo **ít nhất hai instance riêng biệt nhưng bình đẳng về mặt logic**.

Ví dụ một khóa khách hàng được nhận diện bằng `tenant` và `customerId`. Hai `CustomerKey` có cặp trường ấy bằng nhau phải được xem là bằng nhau, dù được tạo ở hai nơi. Cùng một tập dữ liệu sẽ quyết định **cả** `equals()` lẫn `hashCode()`:

~~~java
@Override
public boolean equals(Object obj) {
    if (this == obj) return true;
    if (!(obj instanceof CustomerKey other)) return false;
    return customerId == other.customerId && tenant.equals(other.tenant);
}

@Override
public int hashCode() {
    return Objects.hash(tenant, customerId);
}
~~~

Đoạn trên chỉ là hai phương thức minh họa bên trong lớp có các trường `tenant` và `customerId`; chương trình đầy đủ, chạy độc lập nằm ở phần tiếp theo. Điều thiết yếu không phải bắt buộc dùng `Objects.hash()` mà là **hai phép tính có cùng chính sách bình đẳng**. Có thể viết thuật toán hash khác miễn mọi cặp bằng nhau vẫn có cùng hash.

## 3. Chương trình Java 17: trường hợp đúng và trường hợp sai

Ví dụ có hai lớp khóa:

- `CustomerKey` thực hiện hợp đồng đúng: cả `equals()` và `hashCode()` dùng `tenant`, `customerId`; các trường là `final`.
- `BrokenKey` cố ý sai: `equals()` so sánh tên không phân biệt chữ hoa/chữ thường, nhưng `hashCode()` lại băm chuỗi gốc có phân biệt hoa/thường.

Lưu tệp **HashContractDemo.java** với toàn bộ nội dung sau:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class HashContractDemo {

    static final class CustomerKey {
        private final String tenant;
        private final int customerId;

        CustomerKey(String tenant, int customerId) {
            this.tenant = Objects.requireNonNull(tenant);
            this.customerId = customerId;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof CustomerKey other)) {
                return false;
            }
            return customerId == other.customerId
                    && tenant.equals(other.tenant);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenant, customerId);
        }
    }

    static final class BrokenKey {
        private final String label;

        BrokenKey(String label) {
            this.label = Objects.requireNonNull(label);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof BrokenKey other)) {
                return false;
            }
            return label.equalsIgnoreCase(other.label);
        }

        @Override
        public int hashCode() {
            return label.hashCode(); // Cố ý sai với equalsIgnoreCase().
        }
    }

    static int verifyAllPairs(CustomerKey[] samples) {
        int checks = 0;
        for (CustomerKey left : samples) {
            for (CustomerKey right : samples) {
                checks++;
                if (left.equals(right)
                        && left.hashCode() != right.hashCode()) {
                    throw new AssertionError(
                            "Equal keys must have equal hash codes");
                }
            }
        }
        return checks;
    }

    public static void main(String[] args) {
        CustomerKey a = new CustomerKey("VN", 42);
        CustomerKey b = new CustomerKey(new String("VN"), 42);
        CustomerKey c = new CustomerKey("VN", 43);
        CustomerKey d = new CustomerKey("SG", 42);

        System.out.println("Different objects: " + (a != b));
        System.out.println("Equal keys: " + a.equals(b));
        System.out.println("Equal hash codes: "
                + (a.hashCode() == b.hashCode()));

        Set<CustomerKey> goodSet = new HashSet<>();
        goodSet.add(a);
        System.out.println("HashSet finds equal key: "
                + goodSet.contains(b));

        int checks = verifyAllPairs(
                new CustomerKey[] { a, b, c, d });
        System.out.println("Pair checks passed: " + checks);

        BrokenKey x = new BrokenKey("A");
        BrokenKey y = new BrokenKey("a");
        System.out.println("Broken equals: " + x.equals(y));
        System.out.println("Broken hash codes equal: "
                + (x.hashCode() == y.hashCode()));

        Set<BrokenKey> badSet = new HashSet<>();
        badSet.add(x);
        System.out.println("Broken HashSet finds equal key: "
                + badSet.contains(y));

        System.out.println("Unequal strings can collide: "
                + ("Aa".hashCode() == "BB".hashCode()));
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac HashContractDemo.java
java HashContractDemo
~~~

Kết quả chuẩn:

~~~text
Different objects: true
Equal keys: true
Equal hash codes: true
HashSet finds equal key: true
Pair checks passed: 16
Broken equals: true
Broken hash codes equal: false
Broken HashSet finds equal key: false
Unequal strings can collide: true
~~~

**Phân tích:**

1. `a != b` xác nhận hai khóa là hai object riêng. `new String("VN")` còn tạo một đối tượng chuỗi riêng để kiểm tra bình đẳng theo **giá trị**, thay vì vô tình dựa vào cùng reference.
2. `a.equals(b)` đúng vì `tenant` và `customerId` giống nhau; `Objects.hash(tenant, customerId)` đưa hai khóa bằng nhau đến cùng hash.
3. `goodSet.contains(b)` thành công sau khi thêm `a`, đúng với điều người dùng collection kỳ vọng.
4. Hàm `verifyAllPairs` duyệt 4 × 4 = **16 cặp có thứ tự**. Các cặp bằng nhau phải có hash giống nhau; các cặp khác nhau không bị bắt buộc có hash khác nhau. Kiểm thử này bao gồm cả chiều `(a,b)` và `(b,a)`.
5. Với `BrokenKey("A")` và `BrokenKey("a")`, `equalsIgnoreCase()` trả `true` nhưng `String.hashCode()` của `"A"` và `"a"` khác nhau. `HashSet` có thể không tìm thấy khóa tương đương; trong chương trình này kết quả là `false`.
6. `"Aa"` và `"BB"` là hai chuỗi không bằng nhau nhưng có cùng Java string hash code (2112). Va chạm này hợp lệ và minh họa vì sao **không được viết test yêu cầu hai object khác nhau phải có hash khác nhau**.

`BrokenKey` là **phản ví dụ chủ ý**, không được dùng làm khóa trong hệ thống thực tế.

## 4. Sửa nguyên nhân sai: cùng chuẩn hóa cho equality và hashing

Sai lầm thường gặp là định nghĩa `equals()` không phân biệt hoa/thường nhưng lại băm dữ liệu thô. Không nên sửa bằng cách ngẫu nhiên thay `hashCode()` thành một biểu thức khác mà chưa xác nhận nó tương ứng với cùng quan hệ bình đẳng.

Nếu domain muốn khóa **không phân biệt hoa/thường theo quy tắc chuẩn hóa đã chọn**, có thể chuyển dữ liệu thành một dạng chuẩn tại constructor, rồi để **cả equals và hashCode xử lý chính giá trị chuẩn hóa ấy**:

~~~java
import java.util.Locale;
import java.util.Objects;

final class NormalizedKey {
    private final String normalized;

    NormalizedKey(String raw) {
        normalized = Objects.requireNonNull(raw)
                .toLowerCase(Locale.ROOT);
    }

    @Override
    public boolean equals(Object obj) {
        return obj instanceof NormalizedKey other
                && normalized.equals(other.normalized);
    }

    @Override
    public int hashCode() {
        return normalized.hashCode();
    }
}
~~~

Đây là **lớp minh họa**, chưa phải chương trình `main` độc lập. Trong đó, `new NormalizedKey("API")` và `new NormalizedKey("api")` bằng nhau và có hash bằng nhau. `Locale.ROOT` tránh phụ thuộc locale mặc định của máy khi chuẩn hóa. Quy tắc `toLowerCase(Locale.ROOT)` định nghĩa bình đẳng theo chuỗi sau chuẩn hóa; nó **không nhất thiết tương đương `String.equalsIgnoreCase()` cho mọi Unicode**. Nếu sản phẩm cần so sánh Unicode phức tạp, domain phải chốt rõ thuật toán chuẩn hóa/case folding và dùng **cùng một biểu diễn chuẩn** cho cả hai phương thức.

Một lớp dữ liệu định danh dạng `record` cũng thuận tiện nếu tất cả component có semantics bình đẳng phù hợp:

~~~java
record CustomerId(String tenant, int number) {
    CustomerId {
        Objects.requireNonNull(tenant);
    }
}
~~~

Record Java tự sinh `equals()` và `hashCode()` nhất quán với các component. Tuy nhiên, nếu component là mutable array hay mutable object, record không tự bảo đảm tính bất biến sâu; quy tắc so sánh component, defensive copy và việc thay đổi dữ liệu sau khi làm key vẫn phải xem xét.

## 5. Viết phép kiểm thử đúng cách

### Test một cặp bằng nhau

Một kiểm thử hợp đồng tốt có thứ tự:

1. Chuẩn bị hai instance với cùng dữ liệu định danh, **khác reference**.
2. Xác minh tiền điều kiện: `assertNotSame(a, b)` và `assertEquals(a, b)`. Nếu thiếu `assertEquals(a,b)`, phép kéo theo có thể vượt qua một cách **vô nghĩa** vì hai đối tượng không bằng nhau.
3. Xác minh kết luận: `assertEquals(a.hashCode(), b.hashCode())`.
4. Kiểm thêm `HashSet`/`HashMap` để xác nhận hành vi tích hợp mà hợp đồng này bảo vệ.

Với JUnit Jupiter (JUnit 5), ví dụ sau dùng lớp `HashContractDemo.CustomerKey` của chương trình Java ở trên; cần đưa JUnit Jupiter vào test classpath bằng Maven/Gradle hoặc cấu hình dự án tương ứng:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.HashSet;
import java.util.Set;

class CustomerKeyContractTest {
    @Test
    void equalObjectsMustHaveSameHashCode() {
        var a = new HashContractDemo.CustomerKey("VN", 42);
        var b = new HashContractDemo.CustomerKey("VN", 42);

        assertNotSame(a, b);
        assertEquals(a, b); // Xác minh tiền đề equals() == true.
        assertEquals(a.hashCode(), b.hashCode());

        Set<HashContractDemo.CustomerKey> keys = new HashSet<>();
        keys.add(a);
        assertTrue(keys.contains(b));
    }
}
~~~

Đây là **test class dùng JUnit**, không chạy trực tiếp bằng `java CustomerKeyContractTest`; nó được test runner chạy sau khi thêm dependency. Trường hợp JUnit 5 hiện đại, project có thể dùng nền tảng JUnit Platform thông qua Maven Surefire hoặc Gradle `test`.

### Kiểm thử bằng bảng trường hợp

Đừng chỉ dùng một cặp “happy path”. Chuẩn bị một tập nhỏ nhưng bao quát:

| Trường hợp | Kết quả `equals()` kỳ vọng | Hash assertion |
| --- | --- | --- |
| Hai object riêng, đủ tất cả trường định danh giống nhau | `true` | **Phải bằng nhau** |
| Cùng giá trị tạo từ đường khởi tạo khác (builder, constructor, parser) | `true` nếu domain tương đương | **Phải bằng nhau** |
| Khác một trường được `equals()` xét | `false` | Không áp đặt khác nhau |
| Một trường bị `equals()` bỏ qua | `true` nếu tất cả trường quan trọng giống | **Phải bằng nhau** |
| Chuỗi khác chữ hoa/thường nhưng domain chuẩn hóa chung | `true` theo quy tắc domain | **Phải bằng nhau** |
| Trường có thể `null` | Theo chính sách bình đẳng cho `null` | Nếu bằng nhau thì hash phải bằng |
| Đối tượng bên phải là `null` | `false` | **Không gọi `null.hashCode()`** |
| Hai instance có cùng giá trị, một instance là bản sao sâu | `true` nếu equality theo value | **Phải bằng nhau** |
| Hai đối tượng không bằng nhau nhưng tình cờ cùng hash | `false` | Hợp lệ, không fail |

Có thể duyệt mọi cặp trong tập mẫu, như `verifyAllPairs()` ở chương trình, để dễ phát hiện bất nhất theo tổ hợp. Với project lớn, bổ sung property-based testing: sinh nhiều giá trị domain, **tạo cặp tương đương có chủ đích** và kiểm tra implication; bộ sinh hoàn toàn ngẫu nhiên thường hầu như không tạo được hai khóa bằng nhau nên kiểm thử yếu.

### Đọc đúng mệnh đề kéo theo

Khi lập trình test theo logic:

~~~java
if (a.equals(b)) {
    assert a.hashCode() == b.hashCode();
}
~~~

Đoạn này chỉ minh họa, phụ thuộc bật Java assertions bằng `-ea` và giả định cả hai tham chiếu khác `null`. Nếu `a.equals(b)` luôn là `false` do bug khác, nhánh kiểm tra không chạy mà test vẫn “pass”. Vì thế phải có **test chủ động tạo cặp bằng nhau**, khẳng định `equals() == true` trước rồi mới kiểm hash.

Trong test suite thực tế, dùng `assertEquals(expected, actual)` của framework hoặc ném `AssertionError`; Java keyword `assert` bị vô hiệu mặc định nếu không khởi chạy JVM với `-ea`.

## 6. Những lỗi thiết kế dễ làm test thất bại

### `equals()` xét một tập field, `hashCode()` xét tập field khác

Ví dụ equality so sánh `id` nhưng hash lại tính cả `displayName`. Hai object trùng `id`, khác tên sẽ bằng nhau theo `equals()` mà hash có thể khác. Nếu một field **không tham gia equality** nhưng tham gia hashing, đây là dấu hiệu báo động; thay cả hai theo một khóa logic được thiết kế thống nhất.

Không nhất thiết mọi field `equals()` dùng đều phải xuất hiện trực tiếp trong công thức hash. Một hàm hash luôn trả `0` vẫn bảo toàn điều kiện “equal → same hash”, nhưng gây rất nhiều va chạm và làm giảm hiệu suất bảng băm. Mục tiêu là **đúng hợp đồng trước**, rồi phân phối hash hợp lý.

### Mutable keys trong `HashMap`/`HashSet`

Giả sử khóa có trường `id` mutable và `hashCode()` phụ thuộc `id`. Thêm khóa vào `HashSet` với `id=1`, rồi sửa thành `id=2`. Khi tìm lại, bảng băm có thể tra một bucket khác và không thấy phần tử đã thêm. Đây là lỗi ngay cả khi `equals()` và `hashCode()` **hoàn toàn nhất quán tại từng thời điểm**.

- Ưu tiên key bất biến (`final` fields với immutable values hoặc defensive copies của mutable state).
- Nếu buộc phải sửa dữ liệu định danh, hãy loại key khỏi collection **trước khi sửa** và thêm lại khi đã ở trạng thái mới, với điều kiện quy trình nhất quán và được đồng bộ nếu nhiều luồng cùng truy cập.
- Tránh để code ngoài có thể âm thầm sửa array/list bên trong một key sau khi insert.

Kiểm thử implication trên các instance **ổn định** không thay thế kiểm thử vòng đời của mutable key.

### Mảng và collections

Array Java dùng `Object.equals()` và `Object.hashCode()` nếu không được xử lý đặc biệt, tức chủ yếu theo identity. Nếu một lớp quyết định equality dựa trên **nội dung mảng**, hashing cũng phải dựa trên nội dung tương ứng:

~~~java
import java.util.Arrays;

@Override
public boolean equals(Object obj) {
    return obj instanceof ByteKey other
            && Arrays.equals(bytes, other.bytes);
}

@Override
public int hashCode() {
    return Arrays.hashCode(bytes);
}
~~~

Hai phương thức trên là minh họa trong lớp `ByteKey` có trường `byte[] bytes`; muốn dùng làm key ổn định còn phải copy mảng trong constructor và bảo vệ getter. Với array nhiều chiều, tùy kiểu dữ liệu và semantics cần xét `Arrays.deepEquals()` và `Arrays.deepHashCode()` tương ứng. Với collection, equality và hashing của các implementation chuẩn thường theo nội dung nhưng các phần tử mutable vẫn có thể làm thay đổi cả hai kết quả.

### Kế thừa và so sánh khác kiểu

Một lớp cơ sở cho phép subclass bằng nhau theo `instanceof`, trong khi subclass lại thêm field vào `equals()`, có thể vi phạm đối xứng/bắc cầu. Nếu đang sửa hợp đồng, kiểm tra cả **ai được xem là bằng nhau** lẫn cách tính hash. Với value class `final`, record hoặc quy tắc so kiểu rõ ràng, thiết kế thường dễ kiểm chứng hơn. Đừng chỉ thêm một kiểm thử hash mà bỏ qua tiền đề equality vốn đã sai.

### Số thực, `BigDecimal` và chuẩn hóa

- `BigDecimal("1.0")` và `BigDecimal("1.00")` khác nhau theo `equals()` vì scale khác nhau; `compareTo() == 0` **không đồng nghĩa** `equals() == true`. Viết equality dựa vào `compareTo` nhưng để hash theo `BigDecimal.hashCode()` có thể vi phạm hợp đồng. Nếu domain coi các cách biểu diễn tương đương, cần xác định cách canonicalize cho cả equality lẫn hashing.
- Với `double`/`float`, `NaN`, `+0.0` và `-0.0` có những quy tắc so sánh cần được định nghĩa nhất quán; nên dùng semantics của `Double.equals()/Double.hashCode()` hoặc một quy tắc domain thống nhất, tránh dùng so sánh `==` tùy tiện rồi áp dụng hash khác.
- Với text Unicode, chuẩn hóa, khoảng trắng và phân biệt hoa/thường là **quy tắc nghiệp vụ**. Chỉ thay riêng một bên sẽ dễ tạo cặp equality đúng nhưng hash sai.

## 7. Phân biệt kiểm thử hợp đồng với kiểm thử collision

Đây là hai khía cạnh riêng:

- **Tính đúng:** nếu `equals()` trả `true` thì `hashCode()` phải bằng nhau, không có ngoại lệ.
- **Chất lượng phân phối:** các đối tượng khác nhau lý tưởng phân bố đều để giảm collision, nhưng **không phải yêu cầu logic** của `Object`.

Không nên dùng `assertNotEquals(a.hashCode(), b.hashCode())` để kiểm tra hai object `a` và `b` khác nhau. Bài test đó sẽ có thể thất bại với implementation hoàn toàn hợp lệ. Chẳng hạn `"Aa"` và `"BB"` đã có cùng hash.

Với hệ thống lưu trữ và phân vùng dữ liệu, cũng không nên giả định `Object.hashCode()` là mã định danh ổn định xuyên process/JVM/phiên bản ứng dụng hoặc là hàm băm bảo mật. `hashCode()` phục vụ hợp đồng của đối tượng và collection trong quá trình thực thi, không thay thế canonical ID, checksum hay cryptographic hash.

## 8. Bộ tiêu chí QA khi review `equals()`/`hashCode()`

1. **Đối tượng nào được xem là bằng nhau?** Ghi rõ những field nào tạo thành identity/value equality và quy tắc `null`, chuẩn hóa, kiểu lớp.
2. **Có instance tương đương độc lập?** Tạo `a`, `b` cùng giá trị từ constructor/factory khác nhau; kiểm `a != b` và `a.equals(b)` trước.
3. **Hash của mọi cặp bằng nhau có bằng nhau?** Chạy test ở cả chiều và qua nhiều bộ dữ liệu, gồm giá trị biên, chuỗi Unicode nếu domain hỗ trợ, và trường tùy chọn `null`.
4. **Phần khác nhau có được kiểm đúng?** Khác một field tham gia equality phải khiến `equals()` phản ánh yêu cầu; tuyệt đối không đòi hash phải khác.
5. **Hash có ổn định khi dữ liệu logic không đổi?** Hai lần gọi liên tiếp trên object ổn định cho cùng `int`. Các field dùng làm key tránh mutation.
6. **Tương tác hash collection có đúng?** Sau `set.add(a)`, `set.contains(b)` phải đúng nếu `a.equals(b)`, trong điều kiện keys không bị sửa và collection được dùng đúng hợp đồng.
7. **Có alias đến dữ liệu mutable không?** Array/list/child mutable phải được copy hoặc khóa quyền sửa nếu hash phụ thuộc nội dung.
8. **Các tính chất khác của `equals()`?** Kiểm tra phản xạ, đối xứng, bắc cầu, nhất quán và `equals(null) == false`; hợp đồng hash không thể cứu một equality bị thiết kế sai.

## 9. Bài tập tự kiểm tra

**Bài 1.** Hai object trả `equals() == false` nhưng có cùng `hashCode()`. Có vi phạm hợp đồng không?  
**Đáp án:** Không. Collision hợp lệ; điều kiện chỉ có chiều “equal → same hash”.

**Bài 2.** Một test dùng `if (a.equals(b))` để so hash, nhưng `equals()` bị lỗi và luôn trả `false`. Test đã chứng minh hợp đồng thực tế đúng chưa?  
**Đáp án:** Chưa. Nó chỉ kiểm tra mệnh đề kéo theo theo cách rỗng, chưa xác nhận quan hệ bình đẳng dự kiến. Cần tạo cặp phải bằng nhau và `assertEquals(a,b)` trước.

**Bài 3.** `equals()` dùng `id` còn `hashCode()` dùng cả `id` và `name`. Trường hợp nào sẽ bắt lỗi?  
**Đáp án:** Hai instance có cùng `id` nhưng tên khác nhau. Tiền đề `equals() == true` xảy ra, trong khi hash có thể khác.

**Bài 4.** Vì sao key mutable làm `HashSet.contains()` thất bại dù implementation `equals()` và `hashCode()` nhất quán?  
**Đáp án:** Bảng băm tổ chức mục theo hash tại lúc insert; nếu field định danh đổi sau đó, hash mới có thể dẫn đến vị trí tìm kiếm khác. Cần dùng key bất biến hoặc quản lý remove/update/reinsert an toàn.

**Bài 5.** `String` `"Aa"` và `"BB"` có cùng hash. Có cần sửa Java String không?  
**Đáp án:** Không. Chúng không bằng nhau theo `equals()` nên hash bằng nhau là collision hợp lệ.

**Kết luận thực hành:** Kiểm thử mạnh nhất cho điều kiện này là **tạo nhiều cặp object khác identity nhưng bằng nhau theo domain, xác minh tiền đề `equals() == true`, rồi bắt buộc `hashCode()` bằng nhau**. Kết hợp kiểm thử bảng băm và kiểm soát mutation để phát hiện cả lỗi hợp đồng lẫn hậu quả thực tế.