# Hai giá trị `compareTo()` bằng `0` phải được so sánh nhất quán với giá trị thứ ba

## 1. Quy tắc của thứ tự tự nhiên trong Java

Trong Java, một lớp triển khai `Comparable<T>` định nghĩa **thứ tự tự nhiên** (natural ordering) qua phương thức `int compareTo(T other)`. Phương thức trả một số nguyên:

- **Âm** nếu đối tượng hiện tại đứng trước `other`.
- **`0`** nếu hai giá trị được coi là tương đương theo **thứ tự tự nhiên**.
- **Dương** nếu đối tượng hiện tại đứng sau `other`.

Các giá trị trả về không bắt buộc là `-1`, `0`, `1`; chỉ **dấu** mới có ý nghĩa đối với hợp đồng. Ví dụ `String.compareTo` có thể trả một số âm hoặc dương có trị tuyệt đối lớn hơn `1`.

Điểm quan trọng của bài học: Nếu `x.compareTo(y) == 0`, thì **với mọi `z` có thể so sánh hợp lệ**, dấu của `x.compareTo(z)` và `y.compareTo(z)` phải giống nhau. Nghĩa là, một đối tượng thứ ba không được thấy `x` đứng trước nó nhưng `y` lại đứng sau nó.

Viết chính xác bằng ký hiệu:

```text
x.compareTo(y) == 0
    => signum(x.compareTo(z)) == signum(y.compareTo(z))
       với mọi z thuộc cùng miền so sánh hợp lệ
```

`signum(n)` là dấu của `n`: âm thành `-1`, bằng không thành `0`, dương thành `1`. Trong Java dùng `Integer.signum(n)` để kiểm tra. Hợp đồng **không yêu cầu** `x.compareTo(z)` bằng đúng giá trị số nguyên trả về bởi `y.compareTo(z)`, mà chỉ yêu cầu hai giá trị trả về có **cùng dấu**.

Quy tắc này còn được gọi là **tính thay thế của các giá trị tương đương theo thứ tự**: đã coi `x` và `y` cùng vị trí trong thứ tự, ta phải có thể dùng chúng thay cho nhau trong mọi phép so sánh với `z`.

## 2. Vì sao cần so sánh nhất quán với giá trị thứ ba?

Hãy tưởng tượng có ba giá trị `x`, `y`, `z`:

```text
x.compareTo(y) == 0    // x và y được xếp cùng vị trí
x.compareTo(z) < 0     // x đứng trước z
y.compareTo(z) > 0     // y đứng sau z
```

Ba kết luận trên **mâu thuẫn**: nếu `x` và `y` tương đương theo thứ tự, chúng không thể cùng lúc ở hai phía đối nghịch của `z`. Những thuật toán sắp xếp, tìm nhị phân, cây cân bằng (`TreeSet`, `TreeMap`) và các cấu trúc dùng thứ tự dựa trên giả định rằng các phép so sánh tạo nên một thứ tự hợp lệ.

Không tuân thủ có thể làm kết quả phụ thuộc đường đi của thuật toán: giá trị vừa chèn lại khó tìm, kết quả `contains()` bất ngờ, hoặc những thao tác sắp xếp phức tạp gặp lỗi do hợp đồng so sánh bị vi phạm. Không nên suy đoán một thứ tự cụ thể của `TreeSet` khi triển khai `compareTo` đã sai.

## 3. Những yêu cầu liên quan của `Comparable`

Quy tắc về giá trị thứ ba thuộc hợp đồng lớn hơn. Với các `x`, `y`, `z` cùng miền so sánh hợp lệ:

**Đối xứng về dấu:**

```text
signum(x.compareTo(y)) == -signum(y.compareTo(x))
```

**Bắc cầu:** Nếu `x > y` và `y > z` theo `compareTo`, thì `x > z`; tương tự phía nhỏ hơn.

```text
x.compareTo(y) > 0  &&  y.compareTo(z) > 0
    => x.compareTo(z) > 0
```

**Nhất quán của lớp tương đương với giá trị thứ ba:**

```text
x.compareTo(y) == 0
    => signum(x.compareTo(z)) == signum(y.compareTo(z))
```

Từ các tính chất này, quan hệ `compareTo() == 0` có vai trò một **quan hệ tương đương** trong phép xếp thứ tự: các thành viên trong cùng một nhóm không thể bị một giá trị thứ ba phân biệt về vị trí.

Đừng dùng `return this.score - other.score` để cài đặt so sánh số nguyên: phép trừ có thể **tràn số**, làm đảo dấu và vi phạm hợp đồng. Hãy dùng `Integer.compare(this.score, other.score)` (tương tự với `Long.compare`, `Double.compare` khi phù hợp).

## 4. Ví dụ sai: coi cùng tên là bằng nhau nhưng so tên khác theo tuổi

Giả sử lớp `BadPerson` viết `compareTo` như sau:

```java
@Override
public int compareTo(BadPerson other) {
    if (name.equals(other.name)) {
        return 0;
    }
    return Integer.compare(age, other.age);
}
```

Đây là **một phương thức minh họa trong lớp** có các trường `name` và `age`; chưa phải chương trình độc lập. Ý định có vẻ hợp lý: cùng tên thì như nhau, khác tên thì xếp theo tuổi. Nhưng tiêu chí hai nhánh không tạo ra một thứ tự nhất quán.

Xét ba người:

- `x = ("An", 20)`
- `y = ("An", 30)`
- `z = ("Binh", 25)`

Kết quả so sánh:

| Phép so sánh | Kết quả | Lý do |
| --- | --- | --- |
| `x.compareTo(y)` | `0` | Cùng tên `"An"` |
| `x.compareTo(z)` | `-1` | Khác tên và `20 < 25` |
| `y.compareTo(z)` | `1` | Khác tên và `30 > 25` |

Vì `x` và `y` đã so sánh bằng `0`, cả hai **phải có cùng dấu khi so với `z`**. Một bên `-1`, một bên `1`: đây là lỗi hợp đồng, **dù từng phép so sánh riêng trông có lý**. Lỗi gốc là điều kiện nhận diện “tương đương” dùng tên, còn thứ tự tương quan với người khác lại dùng tuổi.

## 5. Hai cách sửa tùy theo mục tiêu

**Cách A — muốn cùng tên được xem như một nhóm theo thứ tự:** Hãy so sánh **chỉ theo tên** trong mọi trường hợp:

```java
@Override
public int compareTo(BadPerson other) {
    return name.compareTo(other.name);
}
```

Giờ `("An", 20)` và `("An", 30)` cùng cho `0`, còn khi so với `("Binh", 25)`, cả hai đều có dấu âm. Điều kiện với phần tử thứ ba được giữ vững. Tuy nhiên, nếu `equals()` của lớp vẫn xét cả tuổi, thì cách này có thể **không nhất quán với `equals()`** — cần xem phần 7.

**Cách B — muốn phân biệt cả tên và tuổi:** Dùng thứ tự ghép tiêu chí một cách thống nhất: so tên trước; nếu tên bằng nhau, so tuổi.

```java
@Override
public int compareTo(GoodPerson other) {
    int byName = name.compareTo(other.name);
    if (byName != 0) {
        return byName;
    }
    return Integer.compare(age, other.age);
}
```

Khi đó `("An", 20)` và `("An", 30)` **không** còn so sánh bằng `0`, vì tuổi khác nhau. Nếu hai đối tượng có cùng tên **và** cùng tuổi, chúng so sánh bằng `0` và cho dấu như nhau với mọi người thứ ba. Đây cũng là cách làm mà `Comparator.comparing(Person::name).thenComparingInt(Person::age)` thể hiện.

## 6. Chương trình Java 17+ hoàn chỉnh

Lưu mã sau vào `CompareToThirdDemo.java`:

```java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class CompareToThirdDemo {
    record BadPerson(String name, int age)
            implements Comparable<BadPerson> {
        @Override
        public int compareTo(BadPerson other) {
            if (name.equals(other.name)) return 0;
            return Integer.compare(age, other.age);
        }
    }

    record GoodPerson(String name, int age)
            implements Comparable<GoodPerson> {
        @Override
        public int compareTo(GoodPerson other) {
            int byName = name.compareTo(other.name);
            return byName != 0
                    ? byName
                    : Integer.compare(age, other.age);
        }
    }

    public static void main(String[] args) {
        BadPerson x = new BadPerson("An", 20);
        BadPerson y = new BadPerson("An", 30);
        BadPerson z = new BadPerson("Binh", 25);

        System.out.println("bad x-y: "
                + Integer.signum(x.compareTo(y)));
        System.out.println("bad x-z: "
                + Integer.signum(x.compareTo(z)));
        System.out.println("bad y-z: "
                + Integer.signum(y.compareTo(z)));
        System.out.println("bad third consistency: "
                + (Integer.signum(x.compareTo(z))
                == Integer.signum(y.compareTo(z))));

        GoodPerson a = new GoodPerson("An", 20);
        GoodPerson b = new GoodPerson("An", 20);
        GoodPerson c = new GoodPerson("Binh", 25);
        System.out.println("good a-b: "
                + Integer.signum(a.compareTo(b)));
        System.out.println("good a-c: "
                + Integer.signum(a.compareTo(c)));
        System.out.println("good b-c: "
                + Integer.signum(b.compareTo(c)));
        System.out.println("good equals: " + a.equals(b));

        BigDecimal p = new BigDecimal("2.0");
        BigDecimal q = new BigDecimal("2.00");
        BigDecimal r = new BigDecimal("3.0");
        System.out.println("decimal p-q: " + p.compareTo(q));
        System.out.println("decimal p.equals(q): " + p.equals(q));
        System.out.println("decimal p-r sign: "
                + Integer.signum(p.compareTo(r)));
        System.out.println("decimal q-r sign: "
                + Integer.signum(q.compareTo(r)));

        Set<BigDecimal> ordered = new TreeSet<>();
        ordered.add(p);
        ordered.add(q);
        Set<BigDecimal> hashed = new HashSet<>();
        hashed.add(p);
        hashed.add(q);
        System.out.println("TreeSet size: " + ordered.size());
        System.out.println("HashSet size: " + hashed.size());
    }
}
```

Chạy trong thư mục chứa tệp bằng JDK 17 trở lên:

```bash
javac CompareToThirdDemo.java
java CompareToThirdDemo
```

Kết quả:

```text
bad x-y: 0
bad x-z: -1
bad y-z: 1
bad third consistency: false
good a-b: 0
good a-c: -1
good b-c: -1
good equals: true
decimal p-q: 0
decimal p.equals(q): false
decimal p-r sign: -1
decimal q-r sign: -1
TreeSet size: 1
HashSet size: 2
```

Ở `BadPerson`, phép so sánh bằng `0` nhưng hai dấu khi so với `z` khác nhau. Ở `GoodPerson`, những đối tượng trùng cả tên lẫn tuổi được xem là tương đương theo `compareTo` và cũng bằng nhau theo `record.equals()`. Khi so với `c`, dấu đều là `-1`; thuật toán nhất quán.

`BigDecimal` trong ví dụ vừa đảm bảo **quy tắc so sánh với giá trị thứ ba** (`2.0` và `2.00` đều nhỏ hơn `3.0`) vừa là trường hợp quan trọng về **khác biệt giữa `compareTo()` và `equals()`**.

## 7. So với equals: hai yêu cầu có mức bắt buộc khác nhau

**Bắt buộc theo `Comparable`:** nếu `x.compareTo(y) == 0`, mọi `z` hợp lệ phải nhận **cùng dấu** từ `x.compareTo(z)` và `y.compareTo(z)`. Đây là điều kiện đang được minh họa bằng `BadPerson` và `GoodPerson`.

**Khuyến nghị mạnh:** `x.compareTo(y) == 0` nên tương đương `x.equals(y)`. `BigDecimal("2.0")` và `BigDecimal("2.00")` có `compareTo == 0` và `equals == false`, nhưng cả hai vẫn có cùng dấu khi so với `3.0`. Vì vậy, bất nhất với `equals` tự nó **không** vi phạm quy tắc bắt buộc về giá trị thứ ba. Bài tiếp theo xét rủi ro của sự bất nhất này trong `TreeSet` và `TreeMap`.

## 8. Hậu quả thực tế đối với `TreeSet`, `TreeMap`, sắp xếp và tìm kiếm

Với `TreeSet`/`TreeMap`, phép so sánh của `Comparable` (hoặc `Comparator` được cung cấp) phục vụ cả **thứ tự** lẫn việc tìm vị trí một khoá:

- Nếu hai khoá được so sánh bằng `0`, cấu trúc cây xem chúng là cùng khoá theo thứ tự; `TreeMap.put()` có thể cập nhật giá trị gắn với khoá tương đương, còn `TreeSet.add()` có thể không thêm phần tử thứ hai.
- Nếu phép so sánh không bắc cầu hoặc vi phạm quy tắc của giá trị thứ ba, cấu trúc cây có thể có hành vi truy vấn bất ngờ vì việc điều hướng dựa trên các phép so sánh mâu thuẫn.
- Nếu thứ tự không nhất quán với `equals()`, `TreeSet` và `HashSet` có thể đánh giá số phần tử khác nhau dù dùng cùng các đối tượng.
- Thuật toán sắp xếp (`Collections.sort`, `List.sort`, `Arrays.sort`) đòi quan hệ thứ tự đúng hợp đồng; vi phạm có thể khiến kết quả không đáng tin cậy hoặc ném `IllegalArgumentException` trong một số trường hợp.

Không nên kiểm thử tính đúng của `compareTo` chỉ bằng việc chạy `TreeSet` trên vài phần tử rồi quan sát kết quả: thuật toán có thể tình cờ không đi qua trường hợp mâu thuẫn. Hãy **kiểm tra trực tiếp hợp đồng** trên những bộ ba giá trị đại diện.

## 9. Cách thiết kế và kiểm tra `compareTo()`

1. **Xác định tiêu chí nhận diện bằng `0`.** Ví dụ: cùng mã định danh, hay cùng cả tên và tuổi? Những đối tượng có `compareTo == 0` phải hoàn toàn thay thế được nhau trong các phép so sánh tiếp theo.
2. **Chọn thứ tự tiêu chí cố định.** Nếu so theo tên rồi tuổi, dùng tên là tiêu chí đầu tiên; chỉ khi tên bằng nhau mới xét tuổi. Không đổi qua lại giữa hai tiêu chí tùy theo cặp giá trị đang so.
3. **Sử dụng các phương thức so sánh có sẵn.** Chọn `Integer.compare`, `Long.compare`, `String.compareTo`, `Comparator.comparing(...).thenComparing(...)`; tránh tự trừ số nguyên hoặc tự xử lý dấu thủ công khi không cần.
4. **Thống nhất ngữ nghĩa `null`.** `Comparable.compareTo(null)` thông thường phải ném `NullPointerException`; nếu dùng `Comparator`, có thể chủ động chọn quy tắc `Comparator.nullsFirst(...)`/`nullsLast(...)` ở nơi cần hỗ trợ `null`.
5. **Ưu tiên nhất quán với `equals()` khi thiết kế lớp giá trị**, đặc biệt nếu cùng đối tượng làm khoá cho cả collection băm và collection sắp xếp.
6. **Thử bộ ba giá trị.** Với mọi bộ kiểm thử `(x, y, z)` mà `x.compareTo(y) == 0`, xác nhận `Integer.signum(x.compareTo(z)) == Integer.signum(y.compareTo(z))`. Cũng kiểm tra đối xứng dấu và bắc cầu.

Ví dụ kiểm tra giản lược trong một phương thức Java:

```java
static <T extends Comparable<? super T>> boolean samePositionToThird(
        T x, T y, T z) {
    return x.compareTo(y) != 0
            || Integer.signum(x.compareTo(z))
                    == Integer.signum(y.compareTo(z));
}
```

Phương thức trên **chỉ kiểm tra điều kiện với một bộ ba đầu vào**, không chứng minh hợp đồng đúng với *mọi* giá trị có thể có. Biểu thức `x.compareTo(y) != 0` làm điều kiện trở nên đúng theo logic khi tiền đề không thỏa. Cần thêm dữ liệu biên (giá trị trùng, khác nhau, cực trị số nguyên, tiêu chí phụ, chuỗi Unicode, v.v.) và các kiểm tra bắc cầu/đối xứng.

## 10. Các nhầm lẫn thường gặp

| Nhầm lẫn | Giải thích đúng |
| --- | --- |
| `compareTo()` chỉ có thể trả `-1`, `0`, `1` | Kết quả có thể là bất kỳ `int`; quy tắc dùng **dấu** |
| `x.compareTo(y) == 0` chỉ có nghĩa là cặp `x`, `y` tình cờ bằng nhau | Còn bắt buộc phải **cùng dấu so sánh với mọi `z`** |
| Cùng tên thì trả `0`, khác tên thì so tuổi là hợp lý | Tạo ra thứ tự mâu thuẫn khi hai người cùng tên nhưng khác tuổi |
| `compareTo == 0` luôn bắt buộc `equals() == true` | Tính nhất quán với `equals()` được khuyến nghị mạnh, nhưng không tuyệt đối bắt buộc (ví dụ `BigDecimal`) |
| `TreeSet` luôn dùng `equals()` để bỏ trùng | Nó dùng `compareTo` hoặc `Comparator` để xác định vị trí tương đương |
| Có thể `return a - b` với mọi số nguyên | Phép trừ có thể tràn và đảo dấu; dùng `Integer.compare(a, b)` |
| Chỉ kiểm tra xếp thứ tự hai phần tử là đủ | Cần kiểm tra cả quan hệ với **phần tử thứ ba**, bắc cầu và đối xứng |

## 11. Tự kiểm tra

1. Nếu `x.compareTo(y) == 0`, `x.compareTo(z) == -7` và `y.compareTo(z) == -1`, có vi phạm? **Không**, vì cả hai đều âm.
2. Nếu `x.compareTo(y) == 0`, `x.compareTo(z) < 0` nhưng `y.compareTo(z) > 0`, có hợp lệ? **Không**, vì chúng mâu thuẫn về vị trí của `z`.
3. Nếu `new BigDecimal("2.0").compareTo(new BigDecimal("2.00")) == 0` nhưng `equals()` là `false`, điều đó có tự động vi phạm quy tắc giá trị thứ ba không? **Không**. `compareTo` của `BigDecimal` vẫn đặt cả hai cùng vị trí tương quan với mọi số `z`.
4. Vì sao so tên trước, rồi so tuổi nếu tên bằng nhau tốt hơn việc cùng tên trả `0`, khác tên so tuổi? **Vì tiêu chí luôn được áp dụng theo một thứ tự thống nhất, cho phép định nghĩa thứ tự hợp lệ.**

**Ghi nhớ:** `compareTo(x, y) == 0` (viết theo phương thức thể hiện là `x.compareTo(y) == 0`) tạo ra một nhóm **tương đương theo thứ tự**. Mọi thành viên trong nhóm phải so sánh với bất kỳ giá trị thứ ba `z` bằng **cùng một dấu**. Đây là yêu cầu bắt buộc của hợp đồng `Comparable`, độc lập với khuyến nghị `compareTo() == 0` nên nhất quán với `equals()`.