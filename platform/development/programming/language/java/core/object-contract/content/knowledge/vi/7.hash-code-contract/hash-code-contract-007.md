# Vì sao ghi đè `equals()` thường phải ghi đè `hashCode()` cùng lúc?

## 1. Vấn đề cốt lõi

Trong Java, `equals(Object)` trả lời câu hỏi **hai đối tượng có được coi là bằng nhau theo định nghĩa của lớp hay không**. `hashCode()` tạo ra một số nguyên `int` dùng làm mã băm, đặc biệt quan trọng đối với các cấu trúc như `HashMap` và `HashSet`.

Khi bạn ghi đè `equals()` từ so sánh cùng tham chiếu sang so sánh nội dung hoặc mã định danh, hai instance **khác nhau trong bộ nhớ** có thể trở thành bằng nhau. Nếu vẫn để nguyên `hashCode()` kế thừa từ `Object`, bạn không bảo đảm hai instance bằng nhau có cùng mã băm. Điều này vi phạm **hợp đồng của `hashCode()`**, khiến những bộ sưu tập dựa trên hash có thể không tìm thấy khóa, giữ lại phần tử trùng hoặc xử lý khóa không như mong muốn.

Mệnh đề bắt buộc cần nhớ:

**Nếu `a.equals(b)` là `true` thì `a.hashCode() == b.hashCode()` phải là `true`.**

Đảo chiều là sai: hai đối tượng có hash bằng nhau **không bắt buộc** phải bằng nhau theo `equals()`; đó có thể là một lần va chạm hash.

Vì thế, khi thay đổi định nghĩa “bằng nhau” của một lớp, cần xét **đồng thời** cả hai phương thức. Trong cách triển khai thường dùng, bạn ghi đè cả `equals()` và `hashCode()` dựa trên cùng những thuộc tính có ý nghĩa đối với sự bằng nhau.

## 2. Hợp đồng chính xác của hai phương thức

### 2.1. `equals()` phải là một quan hệ tương đương

Với các tham chiếu không `null` và khi những thông tin dùng trong phép so sánh không đổi, một triển khai `equals()` cần bảo đảm:

- **Phản xạ:** `x.equals(x)` luôn là `true`.
- **Đối xứng:** `x.equals(y)` và `y.equals(x)` có cùng kết quả.
- **Bắc cầu:** nếu `x.equals(y)` và `y.equals(z)` đều `true` thì `x.equals(z)` phải `true`.
- **Nhất quán:** gọi lại nhiều lần với cùng thông tin liên quan cho cùng kết quả.
- **So với `null`:** `x.equals(null)` là `false`.

`Object.equals()` mặc định có hành vi so sánh đồng nhất tham chiếu, tương tự `==` với hai tham chiếu đối tượng. Lớp con có thể ghi đè để so theo dữ liệu. Việc ghi đè như vậy mở rộng phạm vi các đối tượng được coi là bằng nhau, nhưng kéo theo nghĩa vụ cập nhật hash tương ứng.

### 2.2. `hashCode()` có những cam kết gì?

Theo hợp đồng Java:

1. Với **cùng một đối tượng**, nếu các thông tin dùng trong `equals()` không bị sửa, nhiều lần gọi `hashCode()` trong **một lần thực thi** phải cho cùng kết quả. Không yêu cầu mã hash giống nhau qua các lần chạy chương trình khác nhau.
2. Nếu `x.equals(y)` trả về `true` thì **bắt buộc** `x.hashCode() == y.hashCode()`.
3. Nếu `x.equals(y)` trả về `false` thì **không bắt buộc** hai hash phải khác nhau. Hash phân biệt tốt giúp hiệu năng nhưng không phải điều kiện đúng/sai của equality.

Viết dưới dạng kéo theo:

```text
equals(a, b) == true  =>  hashCode(a) == hashCode(b)    [BẮT BUỘC]
hashCode(a) == hashCode(b) => equals(a, b) == true      [KHÔNG ĐÚNG]
equals(a, b) == false => hashCode(a) != hashCode(b)     [KHÔNG BẮT BUỘC]
```

`hashCode()` chỉ tạo số nguyên 32-bit và có thể va chạm. Bản thân hash **không phải** ID duy nhất, không phải địa chỉ bộ nhớ và không nên dùng làm định danh nghiệp vụ.

## 3. Vì sao chỉ ghi đè `equals()` dễ làm sai hợp đồng?

Giả sử có một lớp đại diện cho khóa theo `tenantId` và `documentId`:

```java
import java.util.Objects;

// Mảnh code minh họa, chưa phải chương trình độc lập.
final class OnlyEqualsKey {
    private final String tenantId;
    private final String documentId;

    OnlyEqualsKey(String tenantId, String documentId) {
        this.tenantId = tenantId;
        this.documentId = documentId;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OnlyEqualsKey that)) return false;
        return Objects.equals(tenantId, that.tenantId)
            && Objects.equals(documentId, that.documentId);
    }

    // Không ghi đè hashCode(): vẫn kế thừa Object.hashCode().
}
```

Giả sử `first` và `second` là hai instance `OnlyEqualsKey` khác nhau nhưng cùng hai trường:

```java
OnlyEqualsKey first = new OnlyEqualsKey("T1", "D-10");
OnlyEqualsKey second = new OnlyEqualsKey("T1", "D-10");
// first.equals(second) == true
```

Lời gọi `first.equals(second)` cho `true` theo nội dung. Tuy nhiên `Object.hashCode()` mặc định dựa trên danh tính đối tượng. Java **không cam kết** hai instance khác nhau có cùng mã hash; chúng thường cho giá trị khác nhau nhưng va chạm vẫn có thể xảy ra. Vì vậy class này **không bảo đảm** hệ quả bắt buộc “bằng nhau thì hash bằng nhau”.

Đừng viết ví dụ dựa trên kết luận chắc chắn rằng `first.hashCode() != second.hashCode()`: Java không bảo đảm các hash identity luôn khác nhau. Để thấy lỗi bằng kết quả **xác định được**, ví dụ chạy được ở phần sau dùng một kiểu khóa cố ý trả về hai hash khác nhau cho hai đối tượng mà `equals()` coi bằng nhau.

## 4. Cấu trúc `HashMap` và `HashSet` dựa vào cả hash lẫn equality

Ở mức khái niệm:

1. Khi thêm một khóa, cấu trúc băm dùng `hashCode()` để định vị vùng lưu trữ/bucket thích hợp.
2. Trong vùng được xem xét, cấu trúc cần phân biệt những khóa có mã hash trùng bằng quan hệ equality (hoặc trường hợp cùng tham chiếu).
3. Khi truy xuất với một khóa tương đương, nó phải đi tới vị trí tương thích với khóa đã lưu. Nếu hai khóa được coi bằng nhau nhưng có mã hash khác nhau, việc tìm kiếm có thể đi lệch và không bao giờ kiểm tra được phần tử cần tìm.

Chi tiết bucket, thao tác nội bộ và mức độ xử lý va chạm là triển khai; điều phải dựa vào khi lập trình là **hợp đồng `equals/hashCode`**.

| Thao tác | Khi hợp đồng đúng | Khi `equals` nói bằng nhau nhưng hash khác nhau |
| --- | --- | --- |
| `HashSet.add(second)` sau `add(first)` | Phần tử bằng nhau được coi trùng; không tăng số phần tử | Có thể nhận thêm “bản sao” thành phần tử mới |
| `HashSet.contains(second)` | Có thể tìm phần tử tương đương đã thêm | Có thể trả `false` |
| `HashMap.get(second)` sau `put(first, value)` | Tìm ra giá trị của khóa tương đương | Có thể trả `null` dù khóa bằng nhau tồn tại |
| `HashMap.put(second, value2)` | Cập nhật mapping của khóa tương đương | Có thể tạo hai entry cho các khóa được coi bằng nhau |

Các bộ sưu tập dựa trên danh sách như `ArrayList.contains` và các phép so sánh trực tiếp thường dùng `equals()` mà không dựa vào mã băm của phần tử; vì vậy có thể cho kết quả đúng ngay cả khi một lớp có `hashCode()` sai. Không vì vậy mà coi lớp đó hợp lệ: lỗi sẽ xuất hiện khi đổi sang `HashSet` hoặc `HashMap`.

## 5. Chương trình Java 17 hoàn chỉnh: sai rồi sửa

Ví dụ dưới đây trình bày hai lớp khóa.

- `BrokenKey` cố ý **vi phạm hợp đồng**: `equals()` so `code` nhưng `hashCode()` trả về trường `slot` mà equality bỏ qua. Hai instance có cùng `code` và `slot` khác nhau là bằng nhau nhưng có hash khác nhau. Đây là phép mô phỏng **xác định** để dễ quan sát lỗi.
- `CorrectKey` dùng cùng tổ hợp `tenantId` và `code` trong `equals()` lẫn `hashCode()`. `label` chỉ là thông tin mô tả và bị loại khỏi cả hai.

Lưu tệp **`EqualsHashCodeContractDemo.java`**:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class EqualsHashCodeContractDemo {
    static final class BrokenKey {
        private final String code;
        private final int slot;

        BrokenKey(String code, int slot) {
            this.code = Objects.requireNonNull(code);
            this.slot = slot;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof BrokenKey that)) return false;
            return code.equals(that.code); // "slot" không thuộc equality
        }

        @Override
        public int hashCode() {
            return slot; // SAI: field bị equals bỏ qua
        }
    }

    static final class CorrectKey {
        private final String tenantId;
        private final String code;
        private String label;

        CorrectKey(String tenantId, String code, String label) {
            this.tenantId = Objects.requireNonNull(tenantId);
            this.code = Objects.requireNonNull(code);
            this.label = label;
        }

        void rename(String label) {
            this.label = label;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof CorrectKey that)) return false;
            return tenantId.equals(that.tenantId)
                && code.equals(that.code);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenantId, code);
        }
    }

    public static void main(String[] args) {
        BrokenKey badA = new BrokenKey("X-7", 1);
        BrokenKey badB = new BrokenKey("X-7", 2);
        System.out.println("Bad equals: " + badA.equals(badB));
        System.out.println("Bad hashes equal: "
            + (badA.hashCode() == badB.hashCode()));

        Set<BrokenKey> brokenSet = new HashSet<>();
        brokenSet.add(badA);
        brokenSet.add(badB);
        System.out.println("Broken HashSet size: " + brokenSet.size());

        Map<BrokenKey, String> brokenMap = new HashMap<>();
        brokenMap.put(badA, "saved");
        System.out.println("Broken HashMap lookup: " + brokenMap.get(badB));

        CorrectKey a = new CorrectKey("T1", "X-7", "Ban dau");
        CorrectKey b = new CorrectKey("T1", "X-7", "Ban tai lai");
        CorrectKey c = new CorrectKey("T2", "X-7", "Tenant khac");

        System.out.println("Good equals: " + a.equals(b));
        System.out.println("Good hashes equal: "
            + (a.hashCode() == b.hashCode()));
        System.out.println("Different tenant equal: " + a.equals(c));

        Set<CorrectKey> correctSet = new HashSet<>();
        correctSet.add(a);
        correctSet.add(b);
        correctSet.add(c);
        System.out.println("Correct HashSet size: " + correctSet.size());

        Map<CorrectKey, String> correctMap = new HashMap<>();
        correctMap.put(a, "saved");
        System.out.println("Correct HashMap lookup: " + correctMap.get(b));

        a.rename("Da doi ten");
        System.out.println("Contains after rename: " + correctSet.contains(a));
    }
}
```

Biên dịch/chạy từ thư mục chứa tệp bằng **JDK 17 hoặc mới hơn**:

```bash
javac EqualsHashCodeContractDemo.java
java EqualsHashCodeContractDemo
```

Kết quả:

```text
Bad equals: true
Bad hashes equal: false
Broken HashSet size: 2
Broken HashMap lookup: null
Good equals: true
Good hashes equal: true
Different tenant equal: false
Correct HashSet size: 2
Correct HashMap lookup: saved
Contains after rename: true
```

**Giải thích kết quả, không phụ thuộc mã hash ngẫu nhiên:**

1. Hai `BrokenKey` bằng nhau vì cùng `code == "X-7"` về mặt nội dung, nhưng hash lần lượt bằng `1` và `2`. Đây là trường hợp cố ý vi phạm điều kiện “equal implies same hash”.
2. `HashSet` giữ cả hai object vi phạm làm hai phần tử vì chúng có hash khác nhau và được đưa vào vị trí khác nhau; `HashMap.get(badB)` không tìm được entry được thêm bằng `badA`. Không nên suy rộng giá trị hash 1, 2 này thành hành vi chuẩn của `Object.hashCode()`; ví dụ là **một cách tái hiện hậu quả** của lớp có hợp đồng sai.
3. Hai `CorrectKey` cùng `tenantId` và `code` bằng nhau dù `label` khác nhau; hash của chúng cùng được tính bằng `Objects.hash(tenantId, code)`.
4. Object `c` cùng `code` nhưng khác tenant nên **không bằng** `a`. Bỏ `tenantId` khỏi `equals` trong miền này sẽ gộp nhầm hai khóa.
5. `HashSet` đúng chỉ chứa hai khóa khác nhau: `(T1, X-7)` và `(T2, X-7)`. `HashMap.get(b)` tìm ra giá trị đã lưu bằng `a`.
6. Đổi `label` của `a` không làm thay đổi định nghĩa bằng nhau hoặc hash nên khóa vẫn tìm thấy trong tập. Nếu `label` có mặt trong `hashCode()`, đổi tên có thể làm hỏng việc tra cứu khóa.

## 6. Cách triển khai `equals()` và `hashCode()` khớp nhau

### 6.1. Chọn tập trường theo **định nghĩa bằng nhau**

Không tự động đưa tất cả field vào cả hai phương thức. Ví dụ trong `CorrectKey`, khóa là `(tenantId, code)` nên hai phương thức đều được viết theo **hai field này**; `label` không tham gia.

Quy tắc thiết kế:

- **Value object** như cặp tọa độ `(x, y)`: thường so toàn bộ thuộc tính làm nên giá trị.
- **Entity** có ID nghiệp vụ ổn định: có thể so ID; ID có thể là tổ hợp `(tenantId, localId)` khi tính duy nhất có phạm vi.
- **Metadata/cache/log/field mô tả**: không tự động trở thành một phần của equality.
- **Thuộc tính dễ thay đổi**: cân nhắc loại khỏi equality/hash nếu đối tượng sẽ dùng làm khóa trong cấu trúc băm.

Không có yêu cầu rằng `hashCode()` phải sử dụng **mọi** field mà `equals()` dùng; về mặt hợp đồng, có thể trả về mã hash hằng số (mọi object đều hash bằng nhau) và vẫn thỏa “hai object bằng nhau có hash bằng nhau”. Tuy nhiên điều này có thể tạo quá nhiều va chạm, làm giảm hiệu năng. Cách lập trình thực tế thường tính hash từ chính các trường tham gia equality để mã hash hữu ích, rõ ràng và dễ bảo trì. Điều tối quan trọng là **không để những trường mà `equals()` bỏ qua làm thay đổi hash của hai object bằng nhau**.

### 6.2. Lựa chọn công cụ theo kiểu dữ liệu

| Kiểu dữ liệu | So sánh equality phù hợp | Thành phần hash tương ứng |
| --- | --- | --- |
| `int`, `long`, `boolean` | `==` | `Integer.hashCode`, `Long.hashCode`, `Boolean.hashCode` |
| `String`/value object có thể `null` | `Objects.equals(a, b)` | `Objects.hashCode(value)` hoặc hash tổng hợp |
| Nhiều reference có thể `null` | Kết hợp `Objects.equals(...)` bằng `&&` | `Objects.hash(field1, field2, ...)` |
| `float`/`double` | Chọn `Float.compare`/`Double.compare` để khớp chính sách IEEE được định nghĩa; chú ý NaN và zero có dấu | `Float.hashCode`/`Double.hashCode` tương ứng |
| Mảng một chiều | `Arrays.equals(a, b)` | `Arrays.hashCode(array)` |
| Mảng đa chiều khi cần deep equality | `Arrays.deepEquals(a, b)` | `Arrays.deepHashCode(array)` |
| `BigDecimal` | `BigDecimal.equals` theo value **và scale**, hoặc chính sách canonicalization riêng | `BigDecimal.hashCode` nếu dùng `equals` gốc; hash theo giá trị chuẩn hóa nếu dùng equality đã chuẩn hóa |

`Objects.hash(...)` là phương thức varargs; nó hữu ích cho ít trường nhưng có thể gây thêm cấp phát mảng/boxing trong đường chạy nóng. Chỉ tối ưu bằng phép nhân `31` và hàm hash kiểu tương ứng khi có lý do và đã kiểm chứng tính đúng. Ví dụ tổng hợp thủ công:

```java
@Override
public int hashCode() {
    int result = tenantId.hashCode();
    result = 31 * result + code.hashCode();
    return result;
}
```

Mảnh code này thuộc class có hai field `tenantId`, `code` đều được xác nhận không `null`, giống `CorrectKey`; không phải chương trình độc lập. Phép nhân/tràn số nguyên `int` trong tính hash là bình thường và cho kết quả xác định theo Java.

### 6.3. Khi không cần tự triển khai?

Một `record` của Java thường có `equals()` và `hashCode()` được sinh nhất quán từ **các component** của record. Với record làm value object và tất cả component thật sự thuộc định nghĩa bằng nhau, đây là một lựa chọn ngắn gọn. Nhưng nếu component là mảng, logic bằng nhau mặc định không tự trở thành phép so nội dung sâu; nếu một component không thuộc equality nghiệp vụ, code sinh mặc định có thể không phù hợp.

Một lớp không ghi đè **cả** `equals()` **lẫn** `hashCode()` và kế thừa hành vi identity từ `Object` vẫn có hợp đồng nhất quán. Vấn đề xuất hiện khi thay đổi một phía nhưng không đảm bảo phía còn lại tương ứng.

## 7. Những sai lầm tinh vi cần tránh

### 7.1. `hashCode()` không phải phép kiểm tra bằng nhau

Không bao giờ thay `a.equals(b)` bằng `a.hashCode() == b.hashCode()` để quyết định cùng thực thể. Hai object khác nhau có thể đụng hash; Java chỉ cung cấp không gian `int` hữu hạn. Bảng băm vẫn cần đối chiếu khóa theo equality khi có ứng viên trùng hash.

### 7.2. Cùng mã hash không đồng nghĩa cùng đối tượng Java

`System.identityHashCode(obj)` tạo mã hash dựa trên danh tính, không phải địa chỉ RAM và không bảo đảm duy nhất. Trong khi đó `Object.hashCode()` có thể được override bởi lớp con. Để kiểm tra có cùng instance, dùng `a == b` với tham chiếu; để kiểm tra cùng giá trị theo miền, dùng `a.equals(b)` khi lớp thiết kế đúng.

### 7.3. Thay đổi field tham gia hash sau khi đưa vào `HashSet`/`HashMap`

Giả sử `hashCode()` dùng `status` và `status` bị sửa sau `set.add(object)`. Khi `contains(object)` gọi hash mới, việc truy xuất có thể tìm sai vị trí so với lúc thêm. Tương tự với field tham gia `equals()`. Hãy ưu tiên khóa/value object bất biến hoặc chỉ đưa các trường ổn định vào equality/hash.

Từ khóa `final` trên tham chiếu không bảo đảm object được tham chiếu bất biến: `final List<String>` vẫn có thể bị thay đổi các phần tử. Nếu trường là mảng/collection mutable và thực sự tham gia equality, cần phòng vệ bằng sao chép, immutable wrapper hoặc thiết kế phù hợp. 

### 7.4. ID database được gán trễ

Một entity mới có `id == null`. Nếu `equals()` chỉ dùng `Objects.equals(id, that.id)`, hai entity mới khác nhau đều có `null` có thể bị coi bằng nhau; nếu `hashCode()` dựa vào ID rồi ID được gán sau `insert`, hash thay đổi khi đang là khóa. Cần thiết kế nhất quán cho trạng thái trước/sau lưu, tùy hệ thống ORM và chiến lược cấp ID. Đừng cho rằng “đã override đủ hai hàm” thì tự động đúng mọi vòng đời.

### 7.5. Chuẩn hóa không giống nhau giữa equality và hash

Ví dụ `equals()` dùng `code.equalsIgnoreCase(other.code)` nhưng `hashCode()` dùng `code.hashCode()` của chuỗi gốc. Với `"abc"` và `"ABC"`, equality trả `true` nhưng hash gốc có thể khác: hợp đồng bị phá. Nên chuẩn hóa mã trong constructor theo quy tắc miền (chẳng hạn `toUpperCase(Locale.ROOT)` đối với định danh kỹ thuật nếu phù hợp), rồi dùng **cùng biểu diễn chuẩn** trong cả hai phương thức.

Với `BigDecimal`, `new BigDecimal("1.0").compareTo(new BigDecimal("1.00")) == 0` nhưng `equals` mặc định trả `false` vì `scale` khác. Nếu đổi equality sang so trị số bằng `compareTo`, cũng phải tính hash theo chính sách chuẩn hóa cùng trị số; giữ hash `BigDecimal` gốc là nguy hiểm.

### 7.6. Kế thừa phá quy tắc đối xứng

Nếu class cha so hai field, class con lại so ba field, `parent.equals(child)` có thể khác `child.equals(parent)`. Một cách đơn giản cho các class đại diện giá trị là `final class` để cố định quan hệ bằng nhau. Với kế thừa/ORM proxy, cần chiến lược kiểu class nhất quán và phù hợp framework. Tự sinh `hashCode()` không cứu được một triển khai `equals()` mất đối xứng.

### 7.7. Tưởng rằng hash ổn định qua nhiều lần chạy

Hợp đồng chỉ đòi hỏi mã hash nhất quán **trong một lần thực thi** khi các thông tin equality liên quan không đổi. Không nên ghi `hashCode()` hoặc `identityHashCode()` xuống database để làm ID bền vững, không dùng làm khóa chia sẻ liên tiến trình nếu không có hợp đồng thuật toán và dữ liệu rõ ràng. Sử dụng ID miền nghiệp vụ ổn định cho việc đó.

## 8. Cách kiểm tra khi review một lớp

Trước khi chấp nhận một class đã override `equals()`:

1. **Đọc định nghĩa bằng nhau bằng lời:** “Hai instance bằng nhau khi ...”; ghi rõ đó là cùng giá trị hay cùng thực thể theo ID.
2. **Kiểm tra danh sách field được so trong `equals()`:** có bỏ sót namespace, tenant, loại thực thể không? Có đưa nhầm tên hiển thị/cache/trạng thái dễ đổi không?
3. **Kiểm tra hash theo cặp đối tượng bằng nhau:** mọi pair `a.equals(b) == true` bắt buộc cho `a.hashCode() == b.hashCode()`. Tập trường hash không cần giống hệt về cú pháp nhưng phải **tương thích logic**.
4. **Kiểm tra null, kiểu khác, tham chiếu cùng object:** `equals(null)` là `false`, `equals(this)` là `true`; không làm mất đối xứng/bắc cầu.
5. **Kiểm tra tính ổn định:** sau khi đưa object vào `HashSet` hoặc làm key `HashMap`, trường ảnh hưởng equality/hash có bị sửa không?
6. **Kiểm tra bằng collection thật:** thêm hai object bằng nhau vào `HashSet` phải cho một phần tử duy nhất; `HashMap.get(equalKey)` phải trả giá trị đã lưu. Thử với các field khác nhau và hash collision khi phù hợp.
7. **Kiểm tra generated code:** IDE, Lombok và record có thể giúp tránh lỗi gõ, nhưng không tự hiểu quy tắc nghiệp vụ; luôn review trường nào được include/exclude.

Ví dụ những xác nhận tối thiểu (mảnh code áp dụng cho class `CorrectKey` ở trên):

```java
CorrectKey x = new CorrectKey("T1", "D1", "A");
CorrectKey y = new CorrectKey("T1", "D1", "B");
CorrectKey z = new CorrectKey("T2", "D1", "A");

assert x.equals(y);
assert y.equals(x);
assert x.hashCode() == y.hashCode();
assert !x.equals(z);
assert !x.equals(null);
```

Các câu lệnh `assert` chỉ được JVM thực thi khi bật assertions (ví dụ chạy `java -ea ...`); trong kiểm thử tự động nên dùng framework assertion phù hợp. Đây là mảnh minh họa đặt trong phạm vi có thể tham chiếu `CorrectKey`, không phải chương trình Java độc lập.

## 9. Tự kiểm tra

**Câu 1.** `a.equals(b)` trả `true`, nhưng `a.hashCode()` và `b.hashCode()` khác nhau. Chuyện gì sai và ảnh hưởng ở đâu?

**Đáp án:** Lớp vi phạm hợp đồng `hashCode()`. `HashSet` có thể chứa hai phần tử tương đương; `HashMap.get(b)` có thể không tìm được giá trị lưu bằng `a`.

**Câu 2.** Hai object không bằng nhau nhưng hash giống nhau. Có nhất thiết là lỗi không?

**Đáp án:** Không. Va chạm hash được cho phép; hash tốt giảm va chạm vì hiệu năng. Cấu trúc băm vẫn dùng so sánh khóa bằng equality để giải quyết.

**Câu 3.** Nếu không override phương thức nào và dùng `Object.equals/hashCode` mặc định, có vi phạm hợp đồng không?

**Đáp án:** Không. Vì `Object.equals` mặc định chỉ coi cùng instance là bằng nhau, cách hash mặc định tương thích với identity equality. Vấn đề thường đến khi override `equals()` để xem hai instance khác nhau là bằng nhau mà không override hash tương thích.

**Câu 4.** Có thể dùng `hashCode() { return 42; }` cho mọi object không?

**Đáp án:** Về mặt hợp đồng, có: mọi pair bằng nhau chắc chắn cùng hash. Nhưng hiệu năng cấu trúc băm có thể kém đáng kể do mọi khóa dồn vào cùng hash, nên thực tế nên tính hash từ các thành phần equality có ý nghĩa.

**Câu 5.** Một class có `equals()` dựa vào `id` và `hashCode()` dựa vào `(id, lastModified)`. Hai instance có cùng ID nhưng timestamp khác nhau gây lỗi gì?

**Đáp án:** `equals()` nói bằng nhau nhưng hash có thể khác nhau, vi phạm điều kiện bắt buộc. Trường `lastModified` không được ảnh hưởng hash nếu `equals()` bỏ qua nó.

**Câu 6.** Khi override `hashCode()` nhưng giữ `equals()` mặc định, có tự động vi phạm hợp đồng không?

**Đáp án:** Không tự động. Equality theo identity chỉ yêu cầu cùng một instance trả hash nhất quán trong lần thực thi khi thông tin dùng cho equality không đổi. Tuy nhiên, nếu thay đổi hash theo trạng thái mutable trong quá trình đối tượng làm khóa, việc tra cứu vẫn có thể hỏng; và khi đã thiết kế equality theo nội dung thì cần triển khai cả hai một cách đồng bộ.

---

**Ghi nhớ:** `equals()` định nghĩa **ai được coi là bằng ai**; `hashCode()` phải cho cùng giá trị đối với những cặp đó. Ghi đè `equals()` thường buộc bạn ghi đè `hashCode()` để không phá hợp đồng kế thừa từ `Object`. Viết và review hai phương thức như một cặp, chọn tập trường theo ngữ nghĩa, giữ các thành phần đó ổn định và kiểm tra thực tế bằng `HashSet`/`HashMap`.