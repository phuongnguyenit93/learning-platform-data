# Không viết kiểm thử đòi mọi đối tượng khác nhau phải có hash code khác

**Nguyên tắc:** Trong Java, **hai đối tượng bằng nhau theo `equals()` bắt buộc có cùng `hashCode()`; hai đối tượng không bằng nhau hoàn toàn được phép có cùng `hashCode()`**. Vì thế, kiểm thử kiểu `assertNotEquals(a.hashCode(), b.hashCode())` cho mọi cặp `a`, `b` khác nhau là kiểm thử sai hợp đồng. Một hàm hash đúng vẫn có thể tạo ra **hash collision** (va chạm mã băm).

Nội dung này nằm trong **kiểm chứng hợp đồng đối tượng**: mục đích là xác định tính đúng đắn của `equals()`/`hashCode()` và hành vi của các tập hợp dựa trên hash, thay vì áp đặt yêu cầu duy nhất không có trong đặc tả Java.

## 1. Phân biệt đối tượng khác nhau, không bằng nhau và hash khác nhau

Có ba phép so sánh cần phân biệt:

| Biểu thức | Câu hỏi được trả lời | Có bắt buộc kéo theo hash khác nhau? |
| --- | --- | --- |
| `a != b` | Hai biến có trỏ tới **hai đối tượng khác nhau** không? | **Không.** Hai instance riêng vẫn có thể bằng nhau về giá trị hoặc trùng hash. |
| `!a.equals(b)` | Hai đối tượng có **không bằng nhau theo hợp đồng `equals`** không? | **Không.** Hai giá trị khác nhau được phép trùng hash. |
| `a.hashCode() != b.hashCode()` | Hai kết quả hash kiểu `int` có khác nhau không? | Nếu hai hash khác nhau thì `a` và `b` không thể bằng nhau theo một triển khai tuân thủ hợp đồng; chiều ngược lại không đúng. |

Lưu ý `a.equals(b)` chỉ nên gọi khi `a` không phải `null`; nếu cần so sánh có thể `null`, dùng `Objects.equals(a, b)`. Không gọi `hashCode()` trên `null`.

Một trường hợp quen thuộc:

```java
String a = new String("java");
String b = new String("java");
// a != b là true vì khác instance.
// a.equals(b) là true vì cùng nội dung.
// a.hashCode() == b.hashCode() là true theo hợp đồng.
```

Ngược lại, khi `!a.equals(b)` đúng, **không thể kết luận** `a.hashCode() != b.hashCode()`.

## 2. Hợp đồng `hashCode()` yêu cầu điều gì?

Theo API của `java.lang.Object`, kiểm thử nên tập trung vào những điều có tính bắt buộc:

1. **Ổn định trong một lần chạy khi trạng thái dùng cho `equals` không thay đổi:** nhiều lần gọi `hashCode()` trên cùng đối tượng phải trả cùng một số nguyên nếu không có thay đổi ở thông tin sử dụng trong phép so sánh bằng nhau. Không suy ra rằng hash phải cố định giữa hai lần chạy ứng dụng.
2. **Các đối tượng bằng nhau phải có hash bằng nhau:** nếu `a.equals(b)` là `true`, thì `a.hashCode() == b.hashCode()` phải là `true`. Đây là chiều **bắt buộc** của hợp đồng.
3. **Các đối tượng không bằng nhau có thể trùng hash:** nếu `a.equals(b)` là `false`, Java **không yêu cầu** hash phải khác nhau. Hash khác nhau thường giúp hiệu năng bảng băm, nhưng không phải điều kiện hợp lệ.

Viết bằng logic, với `a`, `b` khác `null` và các phương thức hoạt động đúng hợp đồng:

```text
a.equals(b)                         => a.hashCode() == b.hashCode()   [bắt buộc]
a.hashCode() != b.hashCode()         => !a.equals(b)                  [suy ra]
!a.equals(b)                        =/> a.hashCode() != b.hashCode()  [sai]
a.hashCode() == b.hashCode()         =/> a.equals(b)                   [sai]
```

Hợp đồng `equals()` còn yêu cầu **phản xạ, đối xứng, bắc cầu, nhất quán** và `x.equals(null)` là `false`. Khi kiểm chứng hợp đồng đối tượng, các tính chất ấy nên có những kiểm thử riêng; việc hai đối tượng khác nhau có hash khác nhau không nằm trong danh sách.

### Vì sao va chạm không thể bị cấm?

`hashCode()` trả về một `int` 32 bit, nên chỉ có tối đa **2³² giá trị hash có thể biểu diễn**. Trong khi đó, miền các đối tượng hoặc chuỗi có thể có nhiều giá trị phân biệt hơn số đó. Theo nguyên lý chuồng bồ câu, không thể ánh xạ không va chạm tất cả giá trị phân biệt của một miền lớn hơn 2³² vào 2³² kết quả.

Ngay cả trên miền nhỏ, một thuật toán hash bình thường vẫn có thể cho hai giá trị khác nhau cùng mã băm. **Collision không tự động là lỗi**. Ví dụ mã băm hằng số có thể tuân thủ nghĩa vụ `equals/hashCode` nhưng thường phân bố kém và làm giảm hiệu năng.

## 3. Phản ví dụ thật với `String.hashCode()`

Java định nghĩa thuật toán `String.hashCode()` theo các đơn vị mã UTF-16 của chuỗi với hệ số 31. Hai chuỗi:

```text
"Aa": 31 × 65 + 97 = 2112
"BB": 31 × 66 + 66 = 2112
```

Vì vậy `"Aa".equals("BB")` là `false` trong khi cả hai có `hashCode() == 2112`. Đây là va chạm hợp lệ của lớp thư viện chuẩn; không phải bug trong `String`.

**Kiểm thử sai** dưới đây sẽ thất bại mặc dù `String` hoạt động đúng:

```java
// Sai: giả định mọi chuỗi không bằng nhau đều có hash khác nhau.
if ("Aa".hashCode() == "BB".hashCode()) {
    throw new AssertionError("Hash collision bi coi sai thanh loi");
}
```

Kiểm thử đúng có thể xác nhận cả việc hai chuỗi không bằng nhau và việc collision không làm lẫn lộn hai phần tử trong tập hợp. Không được biến điều kiện “không có collision” thành tiêu chuẩn bắt buộc để chấp nhận một triển khai.

## 4. Ví dụ Java 17+ hoàn chỉnh và chạy được

Lưu mã sau thành **`HashCodeContractDemo.java`**. Chương trình cố tình định nghĩa kiểu `Key` có hash luôn là `7` để kiểm chứng rằng các đối tượng không bằng nhau vẫn hoạt động đúng trong `HashSet` và `HashMap`.

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class HashCodeContractDemo {
    // Record sinh equals() theo giá trị 'id'.
    // Hash hằng số gây nhiều collision nhưng KHÔNG vi phạm hợp đồng.
    private record Key(String id) {
        @Override
        public int hashCode() {
            return 7;
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        String firstString = "Aa";
        String secondString = "BB";

        check(!firstString.equals(secondString),
                "Hai chuoi phai khac nhau");
        check(firstString.hashCode() == secondString.hashCode(),
                "Hai chuoi phai co collision theo String.hashCode");

        Key a = new Key("alpha");
        Key equalCopy = new Key("alpha");
        Key b = new Key("beta");

        check(a != equalCopy, "Hai record duoc tao rieng");
        check(a.equals(equalCopy), "Hai key cung id phai bang nhau");
        check(!a.equals(b), "Hai key khac id phai khong bang nhau");

        // Kiem tra bat buoc cua hop dong.
        check(a.hashCode() == equalCopy.hashCode(),
                "Equal objects must have equal hash codes");
        check(a.hashCode() == a.hashCode(),
                "Hash code phai on dinh khi trang thai khong doi");

        // Hai key khac nhau van co the trung hash.
        check(a.hashCode() == b.hashCode(),
                "Vi du co y dung constant hash");

        Set<Key> keys = new HashSet<>();
        keys.add(a);
        keys.add(equalCopy); // Trung theo equals => khong them phan tu moi.
        keys.add(b);         // Khac theo equals => them phan tu thu hai.
        check(keys.size() == 2, "HashSet phan biet theo equals");

        Map<Key, String> map = new HashMap<>();
        map.put(a, "value-alpha");
        map.put(b, "value-beta");
        check(map.size() == 2, "HashMap giu ca hai key khac nhau");
        check("value-alpha".equals(map.get(equalCopy)),
                "Key bang nhau phai tim duoc value");
        check("value-beta".equals(map.get(b)),
                "Key khac nhau phai doc dung value");

        System.out.println("Aa va BB equals: " +
                firstString.equals(secondString));
        System.out.println("Aa hash: " + firstString.hashCode());
        System.out.println("BB hash: " + secondString.hashCode());
        System.out.println("a equals equalCopy: " + a.equals(equalCopy));
        System.out.println("a equals b: " + a.equals(b));
        System.out.println("a va b trung hash: " +
                (a.hashCode() == b.hashCode()));
        System.out.println("HashSet size: " + keys.size());
        System.out.println("HashMap[alpha]: " + map.get(equalCopy));
        System.out.println("HashMap[beta]: " + map.get(b));
    }
}
```

Biên dịch và chạy:

```bash
javac HashCodeContractDemo.java
java HashCodeContractDemo
```

**Standard output chính xác:**

```text
Aa va BB equals: false
Aa hash: 2112
BB hash: 2112
a equals equalCopy: true
a equals b: false
a va b trung hash: true
HashSet size: 2
HashMap[alpha]: value-alpha
HashMap[beta]: value-beta
```

**Phân tích:** `a` và `b` có hash cùng bằng `7` nhưng khác nhau theo `equals()`. `HashSet` lưu cả hai, còn `HashMap` trả về đúng giá trị cho từng khóa. Bản sao `equalCopy` có cùng `id` với `a` nên được nhận là khóa bằng nhau; thêm bản sao vào `HashSet` không tăng kích thước. Ví dụ này phân biệt chính xác **tính đúng đắn** với **chất lượng phân bố hash**. Mã băm hằng số dễ làm bảng băm chậm, nhưng không làm hợp đồng tự mâu thuẫn.

Chương trình có thể được chạy với Java 17 hoặc phiên bản mới hơn hỗ trợ `record`. Tất cả phép `check` được thực thi bình thường, kể cả khi JVM không bật cờ `-ea`; khi điều kiện sai sẽ ném `AssertionError`.

## 5. Sửa kiểm thử JUnit 5 theo đúng hợp đồng

Giả sử mã sản phẩm có lớp `UserId`, trong đó `equals` dùng giá trị mã người dùng và `hashCode` triển khai tương ứng. Hai phép kiểm thử dưới đây **không hợp lệ về nguyên tắc**:

```java
// Sai: "khac object" (a != b) khong bat buoc "khac hash".
assertNotEquals(a.hashCode(), b.hashCode());

// Sai: "khac gia tri" (!a.equals(b)) van co the trung hash.
assertNotEquals(x.hashCode(), y.hashCode());
```

Thay bằng việc kiểm tra **hệ quả bắt buộc** cùng với hành vi của collection:

```java
// Dung: hai doi tuong bang nhau => cung hash.
assertEquals(sameValueA, sameValueB);
assertEquals(sameValueA.hashCode(), sameValueB.hashCode());

// Dung: hai doi tuong khong bang nhau => equals phai phan biet.
assertNotEquals(differentValueA, differentValueB);

// Dung: neu su dung HashSet, phai luu duoc ca hai gia tri khac nhau.
Set<UserId> uniqueIds = new HashSet<>();
uniqueIds.add(differentValueA);
uniqueIds.add(differentValueB);
assertEquals(2, uniqueIds.size());
```

Đây là **mã minh họa trong lớp kiểm thử**: cần `UserId`, các biến được khởi tạo và JUnit Jupiter 5 cùng `java.util.Set/HashSet`. Các câu lệnh trên không phải một chương trình Java độc lập. Trong đó, `assertNotEquals(objectA, objectB)` của JUnit kiểm tra bình đẳng đối tượng, **không** đòi hỏi hash khác.

Một lớp JUnit 5 nhỏ hoàn chỉnh cho hiện tượng collision (giả sử dự án đã cấu hình thư viện JUnit Jupiter):

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;

class HashCollisionTest {
    private record Key(String value) {
        @Override
        public int hashCode() {
            return 42;
        }
    }

    @Test
    void equalKeysMustShareHash() {
        Key first = new Key("A");
        Key equalCopy = new Key("A");

        assertNotSame(first, equalCopy);
        assertEquals(first, equalCopy);
        assertEquals(first.hashCode(), equalCopy.hashCode());
    }

    @Test
    void unequalKeysMayShareHash() {
        Key first = new Key("A");
        Key second = new Key("B");

        assertNotEquals(first, second);
        assertEquals(first.hashCode(), second.hashCode()); // Collision chu dong.
    }

    @Test
    void hashSetMustRetainBothUnequalKeysDespiteCollision() {
        Key first = new Key("A");
        Key equalCopy = new Key("A");
        Key second = new Key("B");

        Set<Key> set = new HashSet<>();
        set.add(first);
        set.add(equalCopy);
        set.add(second);

        assertEquals(2, set.size());
        assertTrue(set.contains(first));
        assertTrue(set.contains(second));
    }
}
```

Trong ví dụ JUnit, `assertEquals(first.hashCode(), second.hashCode())` là **đặc tả riêng của fixture cố tình trả hash hằng số**, nhằm tạo tình huống collision để thử collection. **Không được sao chép assertion ấy làm hợp đồng chung cho mọi lớp**: đối tượng không bằng nhau *được phép* trùng hash, chứ không *bắt buộc* trùng hash.

## 6. Nên kiểm thử những thuộc tính nào?

| Thuộc tính | Cách kiểm chứng đúng | Điều không nên làm |
| --- | --- | --- |
| Phản xạ của `equals` | `assertTrue(a.equals(a))` | Giả sử phép so sánh với `null` hợp lệ khi gọi từ `null`. |
| Đối xứng | Với cặp phù hợp, kiểm tra `a.equals(b) == b.equals(a)` | Chỉ kiểm tra một chiều. |
| Bắc cầu | Nếu `a` bằng `b` và `b` bằng `c`, kiểm tra `a` bằng `c` | Tạo dữ liệu thử không thỏa tiền đề rồi yêu cầu bằng nhau. |
| Nhất quán | Với trạng thái không đổi, gọi lại `equals` và `hashCode` cho kết quả nhất quán | Yêu cầu hash không đổi khi những trường tham gia `equals` đã bị sửa. |
| `null` | Với `a != null`, `assertFalse(a.equals(null))` | Gọi `null.equals(a)`. |
| Equal ⇒ same hash | Tạo **hai instance bằng nhau theo giá trị**, kiểm tra `equals` và hash bằng nhau | Chỉ so cùng một tham chiếu, khiến phép thử quá yếu. |
| Unequal | Tạo giá trị thực sự không bằng nhau, kiểm tra `!equals` | Đòi hash nhất thiết khác nhau. |
| Hành vi hash collection | Thêm hai key không bằng nhau, kiểm tra chúng đều tồn tại; thêm key bằng nhau, kiểm tra không nhân bản | Dùng hash làm tiêu chuẩn duy nhất xác định hai key trùng nhau. |

Khi lớp có những trường **có thể thay đổi** tham gia `equals/hashCode`, tránh sửa khóa sau khi đã đưa vào `HashMap/HashSet`. Việc thay đổi ấy có thể khiến phép tìm kiếm thất bại vì hash hoặc quan hệ bằng nhau của khóa đã thay đổi. Đây là lỗi về cách sử dụng khóa có thể biến đổi, **khác với collision hợp lệ**.

### Nếu viết kiểm thử dựa trên nhiều dữ liệu hoặc property-based testing

Hãy sinh nhiều cặp đối tượng và dùng quy tắc sau:

```java
// Gia ma trong vong lap, a va b khong null:
if (a.equals(b)) {
    if (a.hashCode() != b.hashCode()) {
        throw new AssertionError("Vi pham hop dong equals/hashCode");
    }
}
// Khong co assertion chung nao ve hash neu !a.equals(b).
```

Để phép thử đủ mạnh, nên có các cặp **bằng nhau nhưng khác instance**, các cặp **khác nhau**, và các trường hợp **collision có chủ đích** nếu đối tượng được dùng làm key trong hash collection. Không thể kết luận triển khai chính xác chỉ từ vài ví dụ, nhưng những nhóm dữ liệu ấy giúp phát hiện lỗi hợp đồng thường gặp.

Nếu mục tiêu là đánh giá **hiệu năng hoặc chất lượng hàm băm**, hãy lập kiểm thử khác với dữ liệu đại diện cho ứng dụng, đo tần suất collision, phân bố trong bucket hoặc thời gian thao tác. Đó là tiêu chí hiệu năng có điều kiện, không phải hợp đồng cấm mọi collision. Không biến mục tiêu “phân bố đủ tốt” thành assertion “không bao giờ trùng hash”.

## 7. Các hiểu lầm thường gặp

**“Hai đối tượng khác nhau phải có hash khác nhau vì `hashCode` định danh đối tượng.”** Không đúng. `hashCode()` là mã băm kiểu `int`, không phải định danh duy nhất. Ngay cả `System.identityHashCode(obj)` cũng không hứa trả giá trị duy nhất cho mọi đối tượng.

**“`HashMap` chỉ dùng `hashCode()` để phân biệt key.”** Không đúng. Hash giúp tìm vị trí ứng viên, sau đó collection dùng so sánh phù hợp (trong đó có `equals()`) để nhận diện khóa bằng nhau. Khi hai key không bằng nhau có cùng hash, `HashMap` vẫn có thể lưu cả hai. Cách xử lý nội bộ, như cấu trúc bucket, là chi tiết triển khai không cần thiết để chứng minh hợp đồng.

**“Nếu hash bằng nhau thì `equals()` phải trả true.”** Không đúng. Hash bằng chỉ báo rằng có khả năng cùng giá trị hoặc có collision; phải dùng `equals()` để phân biệt.

**“Một kiểm thử tạo 1.000 đối tượng khác nhau và yêu cầu 1.000 hash khác nhau sẽ phát hiện bug.”** Kiểm thử ấy có thể thất bại trên một triển khai đúng hợp đồng. Nếu phép đo phân bố nằm trong yêu cầu hiệu năng riêng, cần tiêu chí định lượng và dữ liệu phù hợp thay vì quy tắc tuyệt đối.

**“Hai `new Object()` sẽ có hash khác nhau.”** Java không cam kết điều đó, dù nhiều JVM thường tạo các giá trị khác nhau trong ví dụ nhỏ. Không dùng tính quan sát thường gặp làm hợp đồng kiểm thử.

**“Hash giống nhau nghĩa là dữ liệu hai key đã mất.”** Không đúng: collection được thiết kế để xử lý collision. Khi có lỗi mất/truy xuất nhầm key, cần xem lại `equals/hashCode`, trạng thái có thể biến đổi và cách truy cập, thay vì chỉ nhìn việc collision xảy ra.

## 8. Tình huống tự kiểm tra

**Tình huống 1.** `a.equals(b) == true` nhưng `a.hashCode() == 3` và `b.hashCode() == 5`. Có vi phạm không?

**Có.** Hai đối tượng bằng nhau phải có cùng hash. Đây là lỗi hợp đồng.

**Tình huống 2.** `a.equals(b) == false` nhưng `a.hashCode() == b.hashCode() == 7`. Có vi phạm không?

**Không.** Đây là collision hợp lệ. Không viết kiểm thử để buộc hai hash phải khác nhau.

**Tình huống 3.** `a != b` nhưng `a.equals(b) == true`. Nên kiểm tra hash thế nào?

**Kiểm tra bằng nhau.** Hai đối tượng khác tham chiếu có thể bằng nhau theo giá trị; khi bằng nhau thì hash buộc giống nhau.

**Tình huống 4.** Hai chuỗi `"Aa"` và `"BB"` có hash như nhau; đưa vào `HashSet<String>` thì kích thước phải là bao nhiêu?

**Là 2.** Hai chuỗi không bằng nhau theo `String.equals()`, nên collision không hợp nhất chúng thành một phần tử.

**Tình huống 5.** Một lớp luôn trả `hashCode() == 1`, còn `equals()` thực hiện đúng quy tắc bằng nhau. Có được phép không?

**Có về mặt hợp đồng**, vì mọi cặp bằng nhau đều có hash như nhau. Tuy nhiên hash quá kém phân biệt có thể làm giảm hiệu năng các collection dựa trên hash.

## 9. Ghi nhớ và tài liệu chuẩn

Quy tắc ngắn nhất để thiết kế kiểm thử:

- **`equals == true` ⇒ bắt buộc `hashCode` bằng nhau.**
- **`equals == false` ⇒ `hashCode` có thể bằng hoặc khác.**
- **`hashCode` khác nhau ⇒ đối tượng không thể `equals` theo một triển khai tuân thủ hợp đồng.**
- **Collision là hợp lệ; phát hiện lỗi bằng hợp đồng và hành vi truy xuất, không bằng yêu cầu hash duy nhất.**

Tham khảo đặc tả API Java 17:

- [`Object.hashCode()` và `Object.equals()` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html)
- [`String.hashCode()` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#hashCode())
- [`HashMap` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)
- [`HashSet` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)
