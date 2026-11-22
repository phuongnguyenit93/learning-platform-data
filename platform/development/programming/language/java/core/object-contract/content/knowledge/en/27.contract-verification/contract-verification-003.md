# Kiểm thử `equals()`: nhất quán, `null` và đối tượng khác kiểu

## 1. Mục tiêu và bối cảnh

Trong Java, `Object.equals(Object)` trả lời câu hỏi hai đối tượng có **bằng nhau theo quan hệ equality mà lớp định nghĩa** hay không. Bản triển khai mặc định của `Object` kiểm tra danh tính; các lớp giá trị thường ghi đè để so sánh dữ liệu. Một phương thức `equals()` chạy được với hai đối tượng giống nhau vẫn có thể vi phạm hợp đồng khi gặp `null`, đối tượng khác kiểu hoặc khi được gọi nhiều lần.

Bài này tập trung vào ba phép kiểm chứng dễ bị bỏ sót:

1. **Nhất quán (consistency):** cùng một cặp đối tượng, nếu thông tin tham gia so sánh không đổi, các lần gọi `equals()` phải cho cùng kết quả.
2. **So sánh với `null`:** với mọi đối tượng `x` khác `null`, `x.equals(null)` phải trả về `false`, không ném `NullPointerException`.
3. **Đối tượng khác kiểu:** thử các giá trị thuộc kiểu không tương thích với mô hình equality của lớp; với lớp giá trị `AccountKey` trong bài, kết quả phải là `false`, không ném `ClassCastException`.

Ba phép kiểm tra thuộc hợp đồng chung của `Object.equals(Object)`. Để thiết kế đáng tin cậy, còn phải kiểm tra **phản xạ** (`x.equals(x)`), **đối xứng** (`x.equals(y) == y.equals(x)`) và **bắc cầu** (nếu `x == y` và `y == z` theo `equals` thì `x == z`). Dấu `==` trong câu diễn giải này là quan hệ logic, không phải thay thế cho việc gọi `equals()` trong mã.

Nếu một lớp ghi đè `equals()`, hãy rà soát `hashCode()` cùng lúc: **hai đối tượng bằng nhau phải có cùng hash code**. Hai đối tượng không bằng nhau vẫn được phép có hash code trùng nhau.

## 2. Hiểu đúng các tình huống cần kiểm thử

### 2.1. Tính nhất quán có điều kiện

Hợp đồng Java quy định các lần gọi `x.equals(y)` phải cho cùng kết quả **miễn là thông tin được dùng để so sánh trên `x` và `y` chưa thay đổi**. Vì vậy cần kiểm thử cả cặp bằng nhau lẫn cặp không bằng nhau, lặp lại nhiều lần trong cùng trạng thái.

Ví dụ, nếu hai khóa tài khoản cùng `username` và `tenantId`, `equals()` không được phụ thuộc thời gian hiện tại, số ngẫu nhiên, trạng thái bên ngoài hoặc thứ tự gọi phương thức. Nếu một trường dùng trong `equals()` bị sửa, kết quả có thể thay đổi hợp lệ; đó không tự động là vi phạm consistency. Tuy nhiên, đặt một đối tượng có trường khóa thay đổi được trong `HashSet` hoặc làm key của `HashMap` rất nguy hiểm vì vị trí hash có thể không còn phù hợp.

Một phép thử lặp 100 lần giúp phát hiện lỗi phổ biến, nhưng **không thể chứng minh tính đúng đắn cho mọi trạng thái và mọi tương tác**. Thiết kế bất biến và kiểm thử nhiều bộ dữ liệu cung cấp bảo đảm thực tế tốt hơn.

### 2.2. `null` là một đối số hợp lệ của phép so sánh

`a.equals(null)` phải là `false` với `a != null`. Điều này khác với gọi `null.equals(a)`: biểu thức thứ hai không thể dispatch phương thức và sẽ gây `NullPointerException`.

`Objects.equals(a, b)` là tiện ích hỗ trợ hai tham chiếu có thể `null`:

- `Objects.equals(null, null)` trả `true`.
- `Objects.equals(null, a)` trả `false` nếu `a` khác `null`.
- Khi `a` khác `null`, `Objects.equals(a, b)` sử dụng `a.equals(b)`.

Để trực tiếp kiểm tra hợp đồng của phương thức được ghi đè, hãy viết `!a.equals(null)`. Chỉ kiểm tra `Objects.equals(null, a)` sẽ **không gọi** `a.equals(...)` và không phát hiện được lỗi trong phương thức đó.

### 2.3. Đối tượng khác kiểu

Với một value class chỉ chấp nhận cùng kiểu, các lời gọi như `key.equals("alice")` và `key.equals(new Object())` phải trả `false` một cách an toàn. Bước `instanceof` trước khi ép kiểu tránh `ClassCastException`; biểu thức `null instanceof AccountKey` cũng là `false`.

**Lưu ý phạm vi:** hợp đồng `Object.equals()` không bắt buộc *mọi* cặp đối tượng khác lớp đều khác nhau. Một thiết kế đa hình có thể cho phép equality giữa hai lớp khác nhau nếu định nghĩa chặt chẽ và vẫn giữ được đối xứng, bắc cầu, nhất quán. Với khóa tài khoản `final` ở dưới, lựa chọn đúng là chỉ bằng đối tượng `AccountKey`. Không sao chép kỳ vọng “khác class luôn false” sang một thiết kế có yêu cầu equality liên kiểu mà chưa phân tích.

## 3. Ma trận kiểm thử đề xuất

| Trường hợp | Dữ liệu thử | Kết quả mong đợi |
| --- | --- | --- |
| Phản xạ | `a.equals(a)` | `true` |
| Cùng giá trị | `a.equals(b)` với `a` và `b` được tạo riêng nhưng có cùng trường định danh | `true` |
| Khác giá trị | `a.equals(d)` với `tenantId` khác | `false` |
| Nhất quán khi bằng | Lặp `a.equals(b)` khi không đổi trạng thái | Luôn `true` |
| Nhất quán khi không bằng | Lặp `a.equals(d)` khi không đổi trạng thái | Luôn `false` |
| `null` | `a.equals(null)` | `false`, không ngoại lệ |
| Khác kiểu: String | `a.equals("alice")` | `false`, không ngoại lệ |
| Khác kiểu: Object | `a.equals(new Object())` | `false`, không ngoại lệ |
| Đối xứng | `a.equals(b)` và `b.equals(a)` | Hai giá trị giống nhau |
| Bắc cầu | `a.equals(b)`, `b.equals(c)`, `a.equals(c)` | Cả ba là `true` |
| Hash tương thích | `a.equals(b)` là `true` | `a.hashCode() == b.hashCode()` |
| Tích hợp collection | Thêm `a` vào `HashSet`, tra cứu `b` | `contains(b)` là `true` |

Các giá trị `a`, `b`, `c`, `d` phải được dựng rõ ràng, có chủ đích. Kiểm tra một đối tượng với chính nó không đủ phát hiện lỗi so sánh giữa **hai instance khác nhau nhưng bằng giá trị**.

## 4. Ví dụ Java 17+ hoàn chỉnh, có kiểm tra thực thi

`AccountKey` biểu diễn khóa theo tên tài khoản và tenant. Lớp được đánh dấu `final` để quy tắc kiểm tra kiểu bằng `instanceof AccountKey` không phát sinh trường hợp lớp con thay đổi định nghĩa equality. Các trường `final` giữ thông tin tham gia so sánh ổn định sau khi tạo.

```java
// File: EqualsContractTest.java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public final class EqualsContractTest {
    private static final class AccountKey {
        private final String username;
        private final int tenantId;

        AccountKey(String username, int tenantId) {
            this.username = Objects.requireNonNull(username, "username");
            this.tenantId = tenantId;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof AccountKey other)) {
                return false;
            }
            return tenantId == other.tenantId
                    && username.equals(other.username);
        }

        @Override
        public int hashCode() {
            return Objects.hash(username, tenantId);
        }
    }

    private static void check(String name, boolean passed) {
        if (!passed) {
            throw new AssertionError("FAIL - " + name);
        }
        System.out.println("PASS - " + name);
    }

    public static void main(String[] args) {
        AccountKey a = new AccountKey("alice", 7);
        AccountKey b = new AccountKey("alice", 7);
        AccountKey c = new AccountKey("alice", 7);
        AccountKey d = new AccountKey("alice", 8);

        check("phan xa", a.equals(a));
        check("doi xung", a.equals(b) && b.equals(a));
        check("bac cau",
                a.equals(b) && b.equals(c) && a.equals(c));

        boolean equalBefore = a.equals(b);
        boolean differentBefore = a.equals(d);
        boolean consistent = true;
        for (int i = 0; i < 100; i++) {
            if (a.equals(b) != equalBefore
                    || a.equals(d) != differentBefore) {
                consistent = false;
                break;
            }
        }
        check("nhat quan 100 lan",
                equalBefore && !differentBefore && consistent);

        check("khong bang null", !a.equals(null));
        check("khac kieu String", !a.equals("alice"));
        check("khac kieu Object", !a.equals(new Object()));
        check("khac gia tri", !a.equals(d));

        check("hashCode tuong thich",
                a.hashCode() == b.hashCode());

        Set<AccountKey> keys = new HashSet<>();
        keys.add(a);
        check("HashSet tim thay khoa bang nhau", keys.contains(b));
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac EqualsContractTest.java
java EqualsContractTest
```

Đầu ra chính xác với mã trên:

```text
PASS - phan xa
PASS - doi xung
PASS - bac cau
PASS - nhat quan 100 lan
PASS - khong bang null
PASS - khac kieu String
PASS - khac kieu Object
PASS - khac gia tri
PASS - hashCode tuong thich
PASS - HashSet tim thay khoa bang nhau
```

Nếu bất cứ điều kiện nào sai, `check(...)` ném `AssertionError` và chương trình kết thúc thất bại, nên kết quả không phụ thuộc việc bật cờ `-ea`. `a`, `b` và `c` là **ba đối tượng riêng**; `equals()` so sánh giá trị, còn `a == b` là `false`. `d` khác tenant nên không bằng `a`.

Trong `equals(Object)`, `this == obj` là tối ưu hợp lệ cho cùng tham chiếu; `instanceof` xử lý cả `null` lẫn kiểu khác; `hashCode()` sử dụng đúng hai trường mà `equals()` sử dụng. Không cần test rằng hai khóa khác nhau bắt buộc cho hash khác nhau: trùng hash là hợp lệ.

## 5. Các lỗi triển khai mà bộ kiểm thử cần bắt được

### Lỗi 1: Ép kiểu trước khi kiểm tra

Ví dụ **sai** (chỉ là fragment minh họa, không phải chương trình độc lập):

```java
@Override
public boolean equals(Object obj) {
    AccountKey other = (AccountKey) obj;
    return username.equals(other.username)
            && tenantId == other.tenantId;
}
```

Khi `obj` là `null`, truy cập `other.username` ném `NullPointerException`; khi đối tượng khác kiểu, ép kiểu gây `ClassCastException`. Kiểm tra `instanceof` hoặc kiểm tra `null` và class trước khi ép kiểu là cách sửa.

### Lỗi 2: Vô tình overload thay vì override

```java
// SAI: chữ ký khác equals(Object), không ghi đè Object.equals.
public boolean equals(AccountKey other) {
    return other != null
            && username.equals(other.username)
            && tenantId == other.tenantId;
}
```

`a.equals(b)` có thể gọi overload `equals(AccountKey)` và có vẻ đúng, nhưng collection hoặc biểu thức tham chiếu `Object` vẫn dùng `Object.equals(Object)`. Luôn dùng chính xác `public boolean equals(Object obj)` và ghi `@Override`; annotation này giúp trình biên dịch phát hiện chữ ký không ghi đè được phương thức dự kiến.

### Lỗi 3: Bỏ qua một trường định danh hoặc dùng trạng thái thay đổi

Nếu `equals()` chỉ so `username` mà nghiệp vụ yêu cầu thêm `tenantId`, hai tài khoản thuộc tenant khác nhau có thể bị xem là bằng nhau. Kiểm thử `a.equals(d)` trong ví dụ sẽ phát hiện lỗi.

Không tính các trường biến thiên như thời gian hiện tại, lần truy cập gần nhất, bộ đếm hay giá trị ngẫu nhiên vào equality nếu chúng không phải một phần định danh ổn định. Đối tượng dùng làm key trong `HashMap` hoặc phần tử của `HashSet` nên có các trường liên quan equality bất biến trong thời gian lưu trữ.

### Lỗi 4: `equals()` và `hashCode()` bất đồng

Nếu `equals()` cho hai đối tượng khác instance bằng nhau nhưng `hashCode()` vẫn lấy giá trị mặc định từ `Object`, việc tra cứu bằng đối tượng tương đương trong cấu trúc hash có thể thất bại. Hãy kiểm cả quy tắc hash và hành vi `HashSet.contains`/`HashMap.get`, vì đó là nơi lỗi dễ lộ ra nhất.

### Lỗi 5: Thử nghiệm không đủ đường đi

Chỉ gọi `equals()` một lần hoặc chỉ so sánh `a.equals(a)` là chưa đủ. Khi thiết kế test, hãy có ít nhất một cặp bằng theo giá trị nhưng khác tham chiếu, một cặp không bằng, các đối số `null`, nhiều kiểu không tương thích, và các lần gọi lặp.

Đối với lớp có nhiều nhánh hoặc trường nullable, mở rộng ma trận bằng `null` trong từng trường cho phép, mọi tổ hợp giá trị biên, dữ liệu khác biệt tại từng trường, và chiều so sánh đảo ngược. Có thể chuyển các nhóm kiểm tra thành unit test JUnit riêng hoặc parameterized test để khi thất bại biết rõ tình huống.

## 6. Phân biệt các khái niệm thường nhầm

- **`==` với reference:** so danh tính tham chiếu, không tự so giá trị của hai object riêng biệt.
- **`equals(Object)`:** quan hệ equality do lớp cung cấp; mặc định của `Object` gắn với danh tính.
- **`Objects.equals(a, b)`:** tiện ích so sánh null-safe; có thể bỏ qua lời gọi `a.equals` khi `a` là `null`.
- **`hashCode()`:** giá trị phục vụ cấu trúc hash; phải nhất quán với equality, không phải mã định danh duy nhất.
- **`compareTo()`/`Comparator`:** diễn tả thứ tự; tính tương thích với `equals()` cần xét riêng theo nhu cầu của cấu trúc dữ liệu và nghiệp vụ.

**Checklist trước khi chấp nhận một implementation `equals()`:** đúng chữ ký `equals(Object)`; các quy tắc phản xạ–đối xứng–bắc cầu; nhất quán nếu dữ liệu so sánh không đổi; `equals(null) == false`; xử lý an toàn các kiểu không được hỗ trợ; `hashCode` phù hợp; kiểm tra thực tế với collection.

## 7. Tài liệu chuẩn

- [Java SE 26 — `Object.equals(Object)` và `hashCode()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object))
- [Java SE 26 — `Objects.equals(Object,Object)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object))
- [Java SE 26 — `HashSet`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/HashSet.html)
