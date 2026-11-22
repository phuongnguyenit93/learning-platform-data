# Tạo các đối tượng cùng tham chiếu, cùng giá trị và khác giá trị để kiểm chứng hợp đồng Object

## 1. Mục tiêu của phép kiểm chứng

Khi kiểm tra hợp đồng `equals()` và `hashCode()` trong Java, cần tạo **có chủ đích** những đối tượng thuộc ba tình huống khác nhau:

1. **Cùng tham chiếu (same reference):** hai biến trỏ tới chính xác **cùng một đối tượng**; `a == b` là `true`.
2. **Cùng giá trị nhưng khác tham chiếu (equal values, distinct instances):** hai đối tượng được tạo riêng, mang cùng các thuộc tính dùng để định nghĩa tính bằng nhau; `a == b` là `false`, nhưng `a.equals(b)` phải là `true` nếu lớp có ngữ nghĩa so sánh giá trị.
3. **Khác giá trị (different values):** hai đối tượng có ít nhất một thuộc tính tham gia `equals()` khác nhau; `a.equals(b)` phải là `false` với quy tắc bằng nhau đã chọn.

Ba tình huống này là **dữ liệu kiểm thử**, không phải ba loại đối tượng đặc biệt của Java. Tình huống thứ ba nên dùng hai instance khác nhau; nếu giữ nguyên một instance rồi thay đổi trạng thái, bài kiểm chứng còn phát sinh vấn đề về tính biến đổi và vòng đời đối tượng.

Điểm cần phân biệt: Java có **đồng nhất đối tượng** (*identity*) và **bằng nhau về mặt logic** (*logical equality*). Toán tử `==` trên hai biến tham chiếu kiểm tra identity; `equals()` kiểm tra theo triển khai của lớp. `Object.equals()` mặc định cũng so sánh identity cho đến khi lớp ghi đè phương thức này.

## 2. Thiết lập đúng ba nhóm dữ liệu

Giả sử khóa định danh `UserKey` có hai thuộc tính: `id` và `version`; **cả hai** tham gia phép so sánh bằng nhau. Sử dụng các giá trị:

| Biến | Cách tạo | Nội dung | Quan hệ với `first` |
| --- | --- | --- | --- |
| `first` | `new UserKey("U-01", 1)` | `("U-01", 1)` | Đối tượng gốc |
| `alias` | `alias = first` | Cùng dữ liệu và cùng instance | `alias == first` |
| `equalValue` | `new UserKey("U-01", 1)` | `("U-01", 1)` | Khác instance, bằng giá trị |
| `differentValue` | `new UserKey("U-02", 1)` | `("U-02", 1)` | Khác instance, khác giá trị |
| `thirdEqual` | `new UserKey("U-01", 1)` | `("U-01", 1)` | Instance thứ ba bằng giá trị; dùng kiểm tra tính bắc cầu |

Không viết `UserKey equalValue = first;` để kiểm thử **bằng giá trị nhưng khác tham chiếu**: câu lệnh ấy chỉ tạo alias. Ngược lại, `new UserKey(...)` tạo instance riêng biệt nên so sánh `==` với instance cũ là `false` (khi cả hai cùng đang tồn tại).

Để tránh nhầm lẫn do tự động gộp chuỗi/interning hoặc cache của boxed number, ở đây tạo các instance `UserKey` tường minh bằng `new`. Cần định nghĩa `equals()` để xác định chính xác “cùng giá trị” nghĩa là gì trong miền nghiệp vụ.

## 3. Chương trình Java 17+ đầy đủ, chạy được

Lưu mã dưới đây thành tệp `ObjectRelationsDemo.java`. Lớp `UserKey` là immutable: trường `final`, không có setter; `equals()` xét hai thuộc tính và `hashCode()` dùng đúng hai thuộc tính ấy.

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ObjectRelationsDemo {
    static final class UserKey {
        private final String id;
        private final int version;

        UserKey(String id, int version) {
            this.id = Objects.requireNonNull(id, "id");
            this.version = version;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof UserKey other)) {
                return false;
            }
            return version == other.version && id.equals(other.id);
        }

        @Override
        public int hashCode() {
            return Objects.hash(id, version);
        }
    }

    private static void check(String name, boolean condition) {
        if (!condition) {
            throw new AssertionError("FAILED: " + name);
        }
        System.out.println("PASS: " + name);
    }

    public static void main(String[] args) {
        UserKey first = new UserKey("U-01", 1);
        UserKey alias = first;
        UserKey equalValue = new UserKey("U-01", 1);
        UserKey differentValue = new UserKey("U-02", 1);
        UserKey thirdEqual = new UserKey("U-01", 1);

        check("same reference", first == alias);
        check("equal values, different references",
                first != equalValue && first.equals(equalValue));
        check("different values", !first.equals(differentValue));

        check("reflexive", first.equals(first));
        check("symmetric",
                first.equals(equalValue) && equalValue.equals(first));
        check("transitive",
                first.equals(equalValue)
                        && equalValue.equals(thirdEqual)
                        && first.equals(thirdEqual));
        check("not equal to null", !first.equals(null));
        check("equal implies same hash",
                first.hashCode() == equalValue.hashCode());

        Set<UserKey> keys = new HashSet<>();
        keys.add(first);
        keys.add(alias);
        keys.add(equalValue);
        keys.add(differentValue);
        check("HashSet deduplicates equal keys", keys.size() == 2);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac ObjectRelationsDemo.java
java ObjectRelationsDemo
```

Kết quả chuẩn:

```text
PASS: same reference
PASS: equal values, different references
PASS: different values
PASS: reflexive
PASS: symmetric
PASS: transitive
PASS: not equal to null
PASS: equal implies same hash
PASS: HashSet deduplicates equal keys
```

Hàm `check` ném `AssertionError` nếu bất kỳ kiểm tra nào thất bại. Vì vậy các dòng `PASS` là bằng chứng từng điều kiện được thỏa mãn; ví dụ **không phụ thuộc** vào cờ `-ea` của `assert` trong Java.

### Giải thích kết quả

- `alias = first` sao chép **giá trị tham chiếu**, không nhân bản đối tượng. Do đó `first == alias` đúng và `first.equals(alias)` cũng đúng.
- `equalValue = new UserKey("U-01", 1)` tạo instance khác, nên `first != equalValue`; tuy nhiên hai thuộc tính được so sánh bằng nhau, nên `equals()` đúng.
- `differentValue` có `id` khác: `first.equals(differentValue)` sai. Nếu lớp xét `version` trong `equals()`, thay `version` cũng là cách tạo dữ liệu khác giá trị.
- Ba đối tượng `first`, `equalValue`, `thirdEqual` kiểm tra tính **bắc cầu**: khi đối tượng thứ nhất bằng thứ hai và thứ hai bằng thứ ba, đối tượng thứ nhất phải bằng thứ ba.
- Hai đối tượng bằng nhau có hash code bằng nhau theo hợp đồng; ví dụ chỉ khẳng định mệnh đề này, **không** đòi hỏi hai đối tượng khác nhau phải có hash khác nhau.
- `HashSet` giữ hai giá trị logic: khóa `("U-01", 1)` và khóa `("U-02", 1)`; các tham chiếu alias và instance bằng giá trị không tạo thêm phần tử riêng.

## 4. Bảng phân biệt `==`, `equals()` và `hashCode()`

| Cặp so sánh | `==` | `equals()` | Kết luận |
| --- | --- | --- | --- |
| `first` và `alias` | `true` | `true` | Cùng instance; chắc chắn cùng trạng thái hiện tại |
| `first` và `equalValue` | `false` | `true` | Khác instance nhưng bằng logic theo hai thuộc tính |
| `first` và `differentValue` | `false` | `false` | Khác instance và khác logic theo hai thuộc tính |
| `first` và `thirdEqual` | `false` | `true` | Cung cấp đối tượng thứ ba để kiểm chứng tính bắc cầu |
| `first` và `null` | `false` | `false` | `first.equals(null)` phải trả về `false` |

**Lưu ý về hash:** `equals(x, y) == true` kéo theo `x.hashCode() == y.hashCode()`. Chiều ngược lại **không đúng**: hash collision là hợp lệ. Do đó không dùng `hashCode()` làm phép kiểm tra identity hoặc điều kiện đủ cho `equals()`, và không kiểm thử `first.hashCode() != differentValue.hashCode()` như một điều kiện bắt buộc.

Toán tử `==` cũng có thể áp dụng cho **giá trị primitive** như `int`, khi đó nó so sánh giá trị primitive; các ví dụ ở bài này áp dụng `==` cho **biến tham chiếu**.

## 5. Kiểm chứng đầy đủ hợp đồng `equals()` / `hashCode()`

Kiểm thử bằng ba nhóm dữ liệu ở trên tạo nền tảng cho các tính chất của `equals()`:

| Tính chất | Điều kiện cần kiểm tra | Dữ liệu phù hợp |
| --- | --- | --- |
| Phản xạ (*reflexive*) | `x.equals(x)` luôn `true` khi `x != null` | `first` với chính nó |
| Đối xứng (*symmetric*) | `x.equals(y)` và `y.equals(x)` cho cùng kết quả | `first`, `equalValue` |
| Bắc cầu (*transitive*) | `x=y`, `y=z` ⇒ `x=z` theo `equals()` | `first`, `equalValue`, `thirdEqual` |
| Nhất quán (*consistent*) | Không đổi thông tin tham gia so sánh thì kết quả phải ổn định | So lại nhiều lần khi trạng thái không đổi |
| Khác `null` | `x.equals(null)` là `false` với `x != null` | `first`, `null` |
| Hash tương ứng | `x.equals(y)` đúng ⇒ `x.hashCode() == y.hashCode()` | `first`, `equalValue` |
| Hash ổn định | Không đổi thông tin dùng bởi `equals()`, gọi `hashCode()` nhiều lần trong một lần chạy cho kết quả ổn định | `first` bất biến |

Các dòng bổ sung có thể đặt bên trong `main` của chương trình trên để kiểm chứng tính nhất quán (đây là phần **chèn thêm**, không phải một tệp Java riêng):

```java
boolean before = first.equals(equalValue);
boolean after = first.equals(equalValue);
check("consistent equals", before == after);

int firstHash = first.hashCode();
check("stable hash", firstHash == first.hashCode());
```

Dù ví dụ lặp hai lần là phép kiểm tra thực hành dễ hiểu, hai lời gọi đều đúng **không thể chứng minh tuyệt đối** mọi trường hợp của mọi lớp. Kiểm chứng hợp đồng nên chạy với các tập dữ liệu đa dạng, đặc biệt các giá trị biên, `null` nếu được cho phép trong thuộc tính, và các trạng thái có thể thay đổi. Định nghĩa `equals()` phải phản ánh chủ đích của lớp, không chỉ phù hợp một ví dụ.

### Vì sao phải ghi đè cả `equals()` và `hashCode()`?

Các cấu trúc dựa trên hash, như `HashSet` và `HashMap`, dùng hash code để phân nhóm trước khi xác nhận bằng `equals()`. Nếu hai instance được `equals()` coi là bằng nhau nhưng tạo ra hash code khác nhau, tập hợp/bản đồ có thể không tìm thấy phần tử hoặc lưu những phần tử logic bị trùng.

Để giảm sai sót, `UserKey.hashCode()` tính từ đúng `id` và `version`, chính là hai trường được `equals()` xét. Ngược lại, nếu đưa thêm trường không tham gia `equals()` vào `hashCode()`, ta có nguy cơ làm hai đối tượng bằng nhau có hash khác nhau và vi phạm hợp đồng.

## 6. Khi lớp không ghi đè `equals()`

Hai instance chứa các trường giống nhau **không tự động bằng nhau** chỉ vì chúng được tạo bằng cùng tham số:

```java
final class PlainKey {
    final String id;

    PlainKey(String id) {
        this.id = id;
    }
}

PlainKey a = new PlainKey("U-01");
PlainKey b = new PlainKey("U-01");

// a == b            -> false
// a.equals(b)       -> false (kế thừa Object.equals)
// a.equals(a)       -> true
```

Đây là đoạn minh họa đặt trong ngữ cảnh mã Java phù hợp (các câu lệnh tạo biến phải ở bên trong phương thức, constructor hoặc initializer). Vì `PlainKey` không ghi đè `equals()`, biểu thức `a.equals(b)` dùng ngữ nghĩa identity mặc định của `Object`. Nếu mục tiêu là so sánh `id`, hãy triển khai `equals()` cùng `hashCode()`, hoặc dùng kiểu dữ liệu cung cấp so sánh giá trị sẵn có.

### Tùy chọn gọn bằng `record` (Java 17)

`record` tự sinh `equals()` và `hashCode()` dựa trên các thành phần khai báo:

```java
record UserKeyRecord(String id, int version) {}

UserKeyRecord x = new UserKeyRecord("U-01", 1);
UserKeyRecord alias = x;
UserKeyRecord sameValue = new UserKeyRecord("U-01", 1);
UserKeyRecord other = new UserKeyRecord("U-02", 1);

// x == alias                 -> true
// x == sameValue             -> false
// x.equals(sameValue)        -> true
// x.equals(other)            -> false
```

Đây cũng là **mã minh họa**, giả sử các khai báo biến được đặt trong một phương thức. Record không mặc nhiên bảo đảm mọi thành phần đều bất biến sâu: nếu chứa array hoặc đối tượng có thể thay đổi, cần hiểu rõ cách các thành phần ấy thực hiện `equals()` / `hashCode()`. Ví dụ dùng `String` và `int` để hành vi bằng nhau rõ ràng, ổn định.

## 7. Sai lầm thường gặp khi dựng đối tượng kiểm thử

**Nhầm alias với instance bằng giá trị**

```java
UserKey b = a; // a == b là true; chưa hề kiểm thử hai đối tượng khác nhau.
```

Muốn kiểm tra ngữ nghĩa `equals()` giữa hai instance riêng thì tạo `new UserKey(...)` lần thứ hai.

**Dùng `String` literal hoặc boxed number để suy ra identity**

```java
String s1 = "java";
String s2 = "java";
// s1 == s2 có thể là true nhờ string interning;
// kết quả không đại diện cho ngữ nghĩa == của hai đối tượng tùy ý.
```

String literal cùng nội dung được intern theo quy tắc Java. Một số boxed value có thể dùng đối tượng cache, khiến `==` đôi khi đúng. Để kiểm chứng hợp đồng của **kiểu đang học**, hãy tạo instance của đúng kiểu đó, không suy từ hành vi cache của kiểu khác.

**Đổi các trường tham gia hash sau khi thêm vào `HashSet`**

Khi đối tượng dùng làm key bị thay đổi `equals()` / `hashCode()` trong lúc đang nằm trong `HashSet` hoặc `HashMap`, việc tìm kiếm/xóa có thể trở nên sai lệch. Ưu tiên key bất biến như `UserKey` trong chương trình đầy đủ. Nếu cần đối tượng thay đổi, phải thiết kế cách sử dụng trong collection phù hợp.

**So sánh hash như chứng cứ duy nhất**

`hashCode` trùng nhau không chứng minh hai đối tượng bằng nhau; khác hash chứng minh hai đối tượng **không thể bằng nhau nếu lớp tuân thủ hợp đồng**. Không dùng hash để xác định hai biến trỏ cùng instance; `System.identityHashCode()` cũng có thể trùng giữa hai đối tượng khác nhau và không thay cho `==`.

**Quên trường quan trọng trong bộ dữ liệu**

Nếu `equals()` xét `id` và `version`, hãy tạo thêm trường hợp chỉ khác `version`; ngược lại, có thể bỏ sót lỗi `equals()` vô tình so sánh mỗi `id`. Chẳng hạn:

```java
UserKey differentVersion = new UserKey("U-01", 2);
check("different version", !first.equals(differentVersion));
```

Đây là đoạn bổ sung vào `main` chương trình đầy đủ. Đừng viết test đòi hỏi khác giá trị từ một trường **không được quy định** tham gia `equals()`.

## 8. Bộ dữ liệu tối thiểu nên có trong test thật

| Nhóm dữ liệu | Tạo mẫu | Phép kiểm tra chính |
| --- | --- | --- |
| Cùng đối tượng | `alias = first` | `first == alias`, `first.equals(alias)` |
| Hai instance bằng giá trị | `equalValue = new UserKey("U-01", 1)` | `first != equalValue`, `first.equals(equalValue)` |
| Khác trường `id` | `new UserKey("U-02", 1)` | `!first.equals(...)` |
| Khác trường `version` | `new UserKey("U-01", 2)` | `!first.equals(...)` |
| Ba instance bằng giá trị | `first`, `equalValue`, `thirdEqual` | Tính bắc cầu |
| `null` | `first.equals(null)` | Trả `false`, không ném lỗi |
| Collection dựa trên hash | Thêm alias, đối tượng bằng giá trị, đối tượng khác giá trị | Không lưu khóa logic bị trùng |

Không cần kết luận rằng mọi lớp Java phải so sánh theo giá trị. Với đối tượng đại diện một thực thể có identity riêng, `equals()` có thể được thiết kế khác. **Định nghĩa hợp đồng trước, dựng bộ dữ liệu theo hợp đồng đó, rồi kiểm chứng ở cả ba quan hệ tham chiếu/giá trị.**

## 9. Câu hỏi tự kiểm tra

1. Có hai biến `a` và `b` được gán `b = a`. Có thể dùng cặp này để kiểm chứng `equals()` nhận ra hai instance có giá trị giống nhau không? **Không**, vì chỉ có một instance.
2. Hai đối tượng được tạo bằng `new` với cùng thuộc tính. `==` có trả về `true` không? **Không**, chúng là hai instance khác nhau (giả định cả hai tồn tại).
3. Hai instance cùng giá trị có luôn `equals()` bằng `true` không? **Không**: phụ thuộc triển khai; `Object.equals()` mặc định so sánh identity.
4. Nếu `x.equals(y)` đúng, có bắt buộc `x.hashCode() == y.hashCode()` không? **Có**, đó là hợp đồng.
5. Nếu hai hash code bằng nhau, có bắt buộc hai đối tượng bằng nhau không? **Không**, có thể xảy ra collision.
6. Vì sao thêm ba instance bằng giá trị lại hữu ích? **Để kiểm tra tính bắc cầu**, ngoài phản xạ và đối xứng.

**Kết luận thực hành:** dựng ba kiểu quan hệ bằng cách (1) gán alias, (2) tạo một instance mới với cùng các trường quyết định `equals()`, và (3) tạo một instance mới có trường quyết định `equals()` khác đi. Sau đó kiểm tra **`==` để xác định identity**, **`equals()` để xác định bằng logic**, và **`hashCode()` để bảo vệ hợp đồng khi làm việc với các cấu trúc dựa trên hash**.
