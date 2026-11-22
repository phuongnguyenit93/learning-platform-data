# Kiểm thử tính phản xạ, đối xứng và bắc cầu của `equals()` trong Java

`equals(Object)` là phương thức của `java.lang.Object`, được các lớp ghi đè (*override*) khi cần diễn đạt khái niệm **hai đối tượng bằng nhau về mặt giá trị**. Nếu không ghi đè, hành vi `Object.equals()` mặc định tương đương so sánh cùng tham chiếu (`==`). Khi ghi đè, lớp phải tuân theo hợp đồng của `equals()` để kết quả so sánh ổn định và tương thích với các cấu trúc như `HashSet`, `HashMap`.

Ba tính chất cần kiểm thử ở bài này là **phản xạ** (*reflexive*), **đối xứng** (*symmetric*) và **bắc cầu** (*transitive*). Việc thử bằng cả đối tượng giống và khác giá trị, cùng những trường hợp ở ranh giới kiểu kế thừa, quan trọng hơn việc chỉ kiểm tra một cặp đối tượng.

## 1. Phát biểu chính xác ba tính chất

Với các tham chiếu đối tượng khác `null` là `x`, `y`, `z`:

| Tính chất | Quy tắc bắt buộc | Câu hỏi kiểm thử |
| --- | --- | --- |
| **Phản xạ** | `x.equals(x) == true` | Một đối tượng có bằng chính nó không? |
| **Đối xứng** | `x.equals(y) == y.equals(x)` | Đổi chiều so sánh có làm thay đổi kết quả không? |
| **Bắc cầu** | Nếu `x.equals(y)` và `y.equals(z)` đều `true` thì `x.equals(z)` phải `true` | Một chuỗi các đối tượng bằng nhau có nhất quán không? |

Đối xứng có nghĩa **hai chiều cho cùng giá trị Boolean**, kể cả khi cả hai là `false`. Bắc cầu là phép kéo theo: nó chỉ yêu cầu `x.equals(z)` là `true` khi **cả hai điều kiện tiền đề** đều `true`. Không được diễn dịch sai thành “nếu `x` không bằng `y` và `y` không bằng `z` thì `x` phải không bằng `z`”.

Hai đối tượng có giá trị bằng nhau không bắt buộc là cùng tham chiếu: `new Key("A", 1)` và một đối tượng `new Key("A", 1)` khác có thể thỏa `equals() == true` trong khi `==` là `false`.

Hợp đồng `equals()` còn quy định **tính nhất quán** khi thông tin dùng để so sánh chưa thay đổi và `x.equals(null) == false` với mọi `x` khác `null`. Khi `equals()` trả về `true`, `hashCode()` của hai đối tượng cũng phải bằng nhau; chiều ngược lại không bắt buộc đúng. Vì vậy, bài kiểm thử tốt thường kiểm tra cả những điều kiện liên quan này.

## 2. Thiết kế bộ dữ liệu kiểm thử

Không nên chỉ tạo một đối tượng rồi kiểm tra `a.equals(a)`; phép thử đó chưa chạm tới hành vi so sánh **hai instance độc lập**. Với lớp khóa giá trị `Key(code, version)`, nên có ít nhất:

- Ba instance **khác tham chiếu nhưng bằng giá trị**: `a = Key("A", 1)`, `b = Key("A", 1)`, `c = Key("A", 1)`. Nhóm này tạo ra chuỗi `a = b`, `b = c` để kiểm tra bắc cầu thực sự.
- Một instance khác thuộc tính thứ nhất hoặc thứ hai, ví dụ `Key("A", 2)` và `Key("B", 1)`, nhằm bảo đảm việc so sánh cũng trả `false` đúng lúc.
- Trường hợp `null`, giá trị biên (chuỗi rỗng, số 0, số âm) nếu chúng được miền dữ liệu cho phép; với lớp **không final**, bổ sung các kiểu con liên quan.
- Nếu có nhiều trường tạo nên danh tính đối tượng, thay đổi **từng trường** giữa hai mẫu để phát hiện trường bị quên trong `equals()`.

Các phép thử không thể chứng minh một phương thức đúng với mọi đầu vào vô hạn, nhưng chúng xác nhận các quy tắc trên một tập mẫu có chủ đích. Với tập nhỏ, duyệt toàn bộ **cặp** và **bộ ba** làm tăng đáng kể khả năng phát hiện vi phạm so với vài assertion rời rạc.

## 3. Ví dụ Java 17+ độc lập, chạy được

Tạo file **`EqualsContractDemo.java`** với nội dung sau. Lớp `Key` là kiểu giá trị bất biến, khai báo `final` để không phát sinh trường hợp lớp con thay đổi định nghĩa bình đẳng. Phần `NearNumber` cố tình sai hợp đồng để minh họa lỗi bắc cầu.

```java
import java.util.List;
import java.util.Objects;

public class EqualsContractDemo {
    static final class Key {
        private final String code;
        private final int version;

        Key(String code, int version) {
            this.code = Objects.requireNonNull(code);
            this.version = version;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Key other)) {
                return false;
            }
            return version == other.version && code.equals(other.code);
        }

        @Override
        public int hashCode() {
            return 31 * code.hashCode() + version;
        }
    }

    // Cố tình vi phạm tính bắc cầu: gần nhau tối đa 1 đơn vị thì "bằng nhau".
    static final class NearNumber {
        private final int number;

        NearNumber(int number) {
            this.number = number;
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof NearNumber other
                    && Math.abs((long) number - other.number) <= 1;
        }

        @Override
        public int hashCode() {
            return 0; // Cùng hash là hợp lệ, nhưng hiệu năng tra cứu có thể kém.
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void verify(List<Key> values) {
        Key a = values.get(0);
        Key b = values.get(1);
        Key c = values.get(2);

        check(a != b && b != c && a != c,
                "Fixtures must be three distinct instances");
        check(a.equals(b) && b.equals(c),
                "Fixtures must include an equal chain");
        check(!a.equals(values.get(3)), "Version difference not detected");
        check(!a.equals(values.get(4)), "Code difference not detected");
        System.out.println("PASS fixtures");

        for (Key x : values) {
            check(x.equals(x), "Reflexive property failed");
        }
        System.out.println("PASS reflexive");

        int pairCount = 0;
        for (Key x : values) {
            for (Key y : values) {
                pairCount++;
                check(x.equals(y) == y.equals(x), "Symmetry failed");
            }
        }
        System.out.println("PASS symmetric (" + pairCount + " pairs)");

        int tripleCount = 0;
        for (Key x : values) {
            for (Key y : values) {
                for (Key z : values) {
                    tripleCount++;
                    if (x.equals(y) && y.equals(z)) {
                        check(x.equals(z), "Transitivity failed");
                    }
                }
            }
        }
        System.out.println("PASS transitive (" + tripleCount + " triples)");

        for (Key x : values) {
            check(!x.equals(null), "Null comparison failed");
            for (Key y : values) {
                if (x.equals(y)) {
                    check(x.hashCode() == y.hashCode(),
                            "Equal objects must share hashCode");
                }
            }
        }
        System.out.println("PASS null/hashCode");
    }

    public static void main(String[] args) {
        List<Key> values = List.of(
                new Key("A", 1),
                new Key("A", 1),
                new Key("A", 1),
                new Key("A", 2),
                new Key("B", 1));

        verify(values);

        NearNumber x = new NearNumber(1);
        NearNumber y = new NearNumber(2);
        NearNumber z = new NearNumber(3);
        check(x.equals(y) && y.equals(z) && !x.equals(z),
                "Broken example must violate transitivity");
        System.out.println("Broken transitivity: "
                + x.equals(y) + ", " + y.equals(z) + ", " + x.equals(z));
    }
}
```

Biên dịch với JDK 17 trở lên:

```bash
javac -encoding UTF-8 --release 17 EqualsContractDemo.java
java EqualsContractDemo
```

Kết quả stdout mong đợi:

```text
PASS fixtures
PASS reflexive
PASS symmetric (25 pairs)
PASS transitive (125 triples)
PASS null/hashCode
Broken transitivity: true, true, false
```

### Giải thích từng nhóm kiểm thử

**`PASS fixtures`:** ba đối tượng `a`, `b`, `c` có cùng `code/version` nhưng mỗi đối tượng được tạo bằng một lệnh `new` riêng. Việc xác nhận tiền đề này đặc biệt hữu ích: nếu không có ba đối tượng bằng nhau, vòng lặp bắc cầu có thể “đỗ” mà chưa thực sự khảo sát chuỗi các đối tượng khác tham chiếu.

**`PASS reflexive`:** vòng lặp gọi `x.equals(x)` cho cả 5 mẫu, nên một override trả sai khi đối tượng gặp chính nó sẽ bị phát hiện.

**`PASS symmetric (25 pairs)`:** 5 × 5 cặp **có thứ tự** được kiểm tra bằng `x.equals(y) == y.equals(x)`. Đối với một cặp vừa đổi chiều, một phía trả `true` và phía kia trả `false` sẽ gây `AssertionError`. Bao gồm các cặp khác giá trị giúp phát hiện kiểu so sánh bất đối xứng do lớp kế thừa hoặc so sánh sai thuộc tính.

**`PASS transitive (125 triples)`:** 5 × 5 × 5 bộ ba **có thứ tự** được xét. Mỗi khi `x.equals(y) && y.equals(z)` là đúng, kiểm thử yêu cầu `x.equals(z)` đúng. Điều kiện `if` là **định nghĩa logic của hợp đồng**, không phải việc “bỏ qua” kiểm thử; `fixtures` đã bảo đảm có chuỗi dương khác tham chiếu để kiểm tra.

**`PASS null/hashCode`:** thử `x.equals(null)` cho tất cả mẫu và kiểm tra mỗi cặp bằng nhau đều có cùng `hashCode()`. Đây là hai điều kiện hỗ trợ, không thay thế ba quy tắc cốt lõi.

**`Broken transitivity: true, true, false`:** `NearNumber(1)` được xem là bằng `NearNumber(2)`, `NearNumber(2)` bằng `NearNumber(3)`, nhưng `NearNumber(1)` không bằng `NearNumber(3)`. “Gần nhau trong sai số 1” là một **quan hệ không bắc cầu**, vì vậy không thích hợp làm định nghĩa `equals()`. Hàm `hashCode()` trả hằng 0 trong ví dụ này nhằm không tạo thêm một vi phạm `hashCode`; nó vẫn không thể chữa lỗi bắc cầu.

## 4. Những trường hợp dễ khiến `equals()` vi phạm hợp đồng

### 4.1. Bất đối xứng giữa lớp cha và lớp con

Một lỗi quen thuộc: lớp cha cho phép so sánh với mọi lớp con bằng `instanceof Parent`, nhưng lớp con lại chỉ chấp nhận chính kiểu lớp con (ví dụ vì thêm một trường `color`).

```java
// Minh họa hai đoạn điều kiện trong equals(); không phải chương trình độc lập.
// Parent.equals:
return other instanceof Parent p && this.id == p.id;

// Child.equals:
return other instanceof Child c
        && super.equals(other)
        && this.color.equals(c.color);
```

Nếu `p` là `Parent(id=7)` và `c` là `Child(id=7, color="red")`, thì `p.equals(c)` có thể `true` nhưng `c.equals(p)` là `false`. Đây là **vi phạm đối xứng**. Cách tránh đơn giản nếu lớp được thiết kế là kiểu giá trị không cần kế thừa: khai báo lớp `final`. Nếu có kế thừa, phải thiết kế chính sách so sánh kiểu cẩn thận (ví dụ dùng `getClass()` nhất quán theo thiết kế) và thử mọi chiều giữa các kiểu thực tế.

### 4.2. Dùng “gần bằng” làm `equals()`

Làm tròn, so sánh với epsilon, hoặc ngưỡng khoảng cách dễ phá tính bắc cầu. Khi cần so sánh số thực gần đúng, hãy đặt phép so sánh vào **phương thức riêng** như `approximatelyEqual`, nói rõ sai số; đừng mặc nhiên dùng làm `Object.equals()`. Trường hợp `double` còn cần xác định rõ ý nghĩa của `NaN`, `+0.0` và `-0.0`; dùng chiến lược so sánh nhất quán với hàm băm.

### 4.3. Quên trường hoặc phụ thuộc dữ liệu có thể thay đổi

Nếu `equals()` dựa trên `id` và `version` nhưng chỉ so sánh `id`, hai đối tượng lẽ ra khác nhau lại bị coi là bằng. Nếu `equals()` dựa vào các trường có thể thay đổi, kết quả so sánh giữa cùng hai đối tượng có thể thay đổi khi trạng thái đổi. Hợp đồng nhất quán chỉ yêu cầu kết quả ổn định **khi dữ liệu liên quan chưa thay đổi**; tuy nhiên sử dụng đối tượng làm khóa `HashMap` hoặc phần tử `HashSet` rồi thay đổi trường tham gia `equals/hashCode` có thể làm việc tìm kiếm thất bại.

### 4.4. Kiểm thử nhầm chiều hoặc nhầm điều kiện

- Chỉ kiểm tra `assertTrue(a.equals(b))` chưa kiểm tra `b.equals(a)`. Cần đo **cả hai chiều**, nhất là khi các object có kiểu runtime khác nhau.
- Chỉ lặp `x=y=z` cùng một tham chiếu không chứng minh kiểm thử đã phủ bắc cầu qua ba instance riêng.
- Không được đòi `x.equals(z)` khi `x.equals(y)` hoặc `y.equals(z)` là `false`; tiền đề bắc cầu không xảy ra.
- `Objects.equals(a,b)` giúp so sánh an toàn khi có `null`, nhưng bản thân tiện ích này **không sửa** được `equals()` bất đối xứng hoặc không bắc cầu của các đối tượng.
- Không dùng mỗi `assertEquals(a,b)` để kết luận đối xứng: framework sẽ đi qua một lệnh so sánh mà không tự động kiểm tra cả hai chiều theo hợp đồng.

## 5. Đưa vào bộ kiểm thử dự án

Trong JUnit 5, ba tính chất có thể diễn đạt bằng các test riêng sử dụng cùng fixture (ví dụ `List<Key> samples`), cùng tư duy như vòng lặp thuần Java ở trên:

```java
// Đoạn minh họa bên trong một lớp test JUnit 5 đã có samples.
@Test
void reflexive() {
    for (Key x : samples) {
        assertTrue(x.equals(x));
    }
}

@Test
void symmetric() {
    for (Key x : samples) {
        for (Key y : samples) {
            assertEquals(x.equals(y), y.equals(x));
        }
    }
}

@Test
void transitive() {
    for (Key x : samples) {
        for (Key y : samples) {
            for (Key z : samples) {
                if (x.equals(y) && y.equals(z)) {
                    assertTrue(x.equals(z));
                }
            }
        }
    }
}
```

Đây là **đoạn minh họa**, cần import `org.junit.jupiter.api.Test` và các assertion từ `org.junit.jupiter.api.Assertions`, khai báo `Key`/`samples` trong lớp test và cấu hình JUnit 5 trong dự án. Chương trình ở mục 3 là ví dụ **đầy đủ, không cần thư viện ngoài** để biên dịch và chạy ngay.

Với lớp thực tế có nhiều dạng đầu vào, tăng độ phủ bằng kiểm thử tham số hóa hoặc sinh dữ liệu (*property-based testing*): kiểm tra các đối tượng được tạo độc lập, mọi biến thể trường tạo danh tính, giá trị biên, kiểu con (nếu có) và các lần gọi lặp lại khi trạng thái không đổi. Luôn thêm ít nhất một fixture bảo đảm hai instance độc lập **được kỳ vọng bằng nhau**, và một bộ ba độc lập **có tiền đề bắc cầu đúng**; nếu không, nhiều assertion có thể đúng một cách rỗng.

## 6. Checklist khi review `equals()`

1. `x.equals(x)` luôn trả `true` với `x != null`?
2. `x.equals(y)` và `y.equals(x)` luôn cùng kết quả, kể cả khi hai đối tượng thuộc các kiểu có quan hệ kế thừa?
3. Khi `x.equals(y)` và `y.equals(z)` là `true`, `x.equals(z)` có `true`? Đã thử **ba đối tượng khác tham chiếu** chưa?
4. `x.equals(null)` trả `false`, kết quả có ổn định khi dữ liệu không đổi, và các cặp bằng nhau có cùng `hashCode()`?
5. Bộ fixture đã phủ cả trường hợp **bằng** và **khác**, sự thay đổi từng thuộc tính quan trọng và các trường hợp biên của bài toán?

Một kiểm thử `equals()` đáng tin cậy phải bắt được cả lỗi “hai đối tượng bằng nhau bị xem là khác” lẫn lỗi vi phạm logic của quan hệ bằng nhau; đồng thời không nhầm tính bắc cầu với phép so sánh gần đúng.