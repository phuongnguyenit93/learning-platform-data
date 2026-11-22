# Giới hạn đệ quy với Comparable<T>

## 1. Bài toán: tìm giá trị lớn hơn nhưng vẫn giữ đúng kiểu

Giả sử cần một phương thức nhận hai giá trị cùng kiểu và trả về giá trị lớn hơn. Dùng `Object` không đủ: không phải đối tượng nào cũng có một thứ tự tự nhiên để so sánh.

Java dùng interface `Comparable<T>` để mô tả khả năng so sánh một đối tượng với đối số có kiểu `T`. Phương thức quan trọng là:

```java
// Trích dạng khai báo để giải thích hợp đồng, không cần tự viết lại interface JDK.
int compareTo(T other);
```

Ví dụ, `String` thực hiện `Comparable<String>`; một chuỗi có thể so sánh với chuỗi khác theo thứ tự tự nhiên của nó.

Một phương thức generic có thể yêu cầu khả năng này:

```java
// Phương thức minh họa, đặt bên trong một lớp.
static <T extends Comparable<T>> T strictMax(T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
```

Đây là **giới hạn đệ quy** (recursive bound): tham số kiểu `T` xuất hiện trong chính giới hạn `Comparable<T>` của nó. Cách diễn đạt này còn được gọi là F-bounded polymorphism.

Tên gọi có thể lạ, nhưng mục tiêu cụ thể là đơn giản: trình biên dịch cần biết rằng một giá trị `T` có thể gọi `compareTo` với một giá trị `T` khác.

## 2. Đọc giới hạn theo từng phần

Với `<T extends Comparable<T>>`:

1. `T` là tham số kiểu do phương thức khai báo.
2. `extends` đặt giới hạn trên cho `T`; trong tham số kiểu, từ này cũng dùng khi giới hạn là interface.
3. `Comparable<T>` yêu cầu hợp đồng so sánh nhận đối số kiểu `T`.
4. Vì `second` có kiểu `T`, lời gọi `first.compareTo(second)` được kiểm tra hợp lệ.
5. Hai nhánh trả về `first` hoặc `second`, nên kết quả vẫn có kiểu `T`.

Đừng đọc chữ ký như “`T` kế thừa chính nó”. `T` phải thỏa một kiểu interface được tham số hóa bằng `T`; giới hạn là `Comparable<T>`, không phải trực tiếp là `T`.

Cũng không có đệ quy khi chạy ở phương thức `strictMax`: nó gọi `compareTo` một lần và chọn một trong hai đối số. Từ “đệ quy” mô tả cấu trúc ràng buộc kiểu, không mô tả một vòng gọi hàm vô hạn.

Những quy tắc này vẫn dùng trong Java hiện đại. Phần thực hành dùng Java 17 trở lên và các API chuẩn.

## 3. Vì sao <T> đơn thuần chưa đủ?

Nếu bỏ giới hạn:

```java
// Minh họa lỗi; không biên dịch.
static <T> T wrongMax(T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
```

Một `T` không bị ràng buộc có thể là một kiểu không có `compareTo`. Thân phương thức generic phải hợp lệ cho mọi đối số kiểu mà khai báo cho phép, không chỉ cho những lần gọi với `String` hoặc `Integer`.

Giới hạn cũng giữ quan hệ giữa hai kiểu: không chỉ cần “có một `compareTo` nào đó”, mà cần phép so sánh chấp nhận đúng kiểu đầu vào mà phương thức sẽ cung cấp.

Một lớp thực hiện `Comparable<String>` không tự động trở thành đối tượng so sánh được với chính kiểu lớp đó. Đối số của `Comparable` mô tả kiểu được nhận vào khi so sánh; tên interface một mình không đủ để suy ra quan hệ tự so sánh.

## 4. Hợp đồng compareTo: xét dấu, không đòi đúng -1 hoặc 1

`compareTo` trả về:

- Số âm khi đối tượng hiện tại đứng trước đối số.
- `0` khi hai đối tượng bằng nhau theo thứ tự so sánh.
- Số dương khi đối tượng hiện tại đứng sau đối số.

Chỉ xét dấu của kết quả. Không viết:

```java
// Cách kiểm tra không đúng với hợp đồng tổng quát của Comparable.
if (first.compareTo(second) == 1) {
    // Không bao quát mọi kết quả dương hợp lệ.
}
```

Dùng `> 0`, `< 0` hoặc `>= 0` tùy yêu cầu.

Một thứ tự hợp lệ còn cần tính nhất quán về dấu khi đảo hai đối số, tính bắc cầu và cách xử lý các phần tử so sánh bằng nhau. Trình biên dịch không chứng minh các tính chất này chỉ từ việc một lớp khai báo `implements Comparable<...>`.

Khi so sánh trường số nguyên, dùng `Integer.compare(a, b)` thường rõ hơn phép trừ `a - b`, vì phép trừ có thể tràn số và làm sai dấu.

Theo hợp đồng `Comparable`, so sánh với `null` gây `NullPointerException`. Một phương thức tổng quát nên nêu rõ chính sách `null`; chương trình bên dưới chủ động từ chối hai đối số `null` trước khi so sánh.

## 5. Giới hạn chặt và vấn đề với lớp con

Giả sử:

```java
// Khai báo minh họa; các phần triển khai còn lại được trình bày ở chương trình đầy đủ.
class Score implements Comparable<Score> {
    @Override
    public int compareTo(Score other) {
        return 0;
    }
}

class RatedScore extends Score {
}
```

Trong đoạn minh họa này, `compareTo` chỉ trả về `0` để làm rõ hình dạng kiểu; không phải thuật toán so sánh điểm hoàn chỉnh.

`RatedScore` kế thừa hợp đồng `Comparable<Score>`. Nó có thể so sánh với một `Score`; một `RatedScore` khác cũng là `Score`, nên phép so sánh giữa hai đối tượng con có ý nghĩa.

Tuy nhiên, `RatedScore` không thực hiện `Comparable<RatedScore>`. Kiểu generic không tự đổi đối số `Score` thành `RatedScore` khi có một lớp kế thừa.

Nếu buộc chọn `T = RatedScore` cho `strictMax`, giới hạn không thỏa:

```java
// Minh họa lỗi, với strictMax nằm trong Tools và có các biến a, b kiểu RatedScore.
RatedScore selected = Tools.<RatedScore>strictMax(a, b);
```

Lý do không phải hai đối tượng không so sánh được về mặt nghiệp vụ. Lý do là chữ ký đang yêu cầu hợp đồng chặt `Comparable<RatedScore>`, còn lớp con kế thừa `Comparable<Score>`.

### Lưu ý về suy luận kiểu

Không nên kết luận mọi lời gọi `strictMax(a, b)` với hai `RatedScore` đều thất bại.

Nếu không buộc kiểu kết quả phải là `RatedScore`, trình biên dịch có thể chọn `T = Score`. Khi đó:

```java
// Minh họa hợp lệ trong ngữ cảnh có các khai báo tương ứng.
Score selected = Tools.strictMax(a, b);
```

Kết quả được nhìn qua `Score`. Vấn đề thể hiện rõ khi cần giữ kiểu kết quả là `RatedScore` hoặc khi chỉ định `<RatedScore>` tường minh.

## 6. Dạng linh hoạt: T extends Comparable<? super T>

Một chữ ký thường phù hợp hơn cho thuật toán dùng thứ tự tự nhiên:

```java
// Phương thức minh họa, đặt bên trong một lớp.
static <T extends Comparable<? super T>> T max(T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
```

Đọc `Comparable<? super T>` là: đối tượng `T` có khả năng so sánh với một kiểu phù hợp là `T` hoặc một kiểu cha của `T`.

Vì phương thức so sánh chấp nhận kiểu cha, đưa một giá trị `T` vào là an toàn. Đó là lý do dấu `super` phù hợp ở vị trí đầu vào này.

Trong ví dụ:

- Chọn `T = RatedScore`.
- `Score` là kiểu cha của `RatedScore`.
- `RatedScore` có `Comparable<Score>` kế thừa.
- Do đó nó thỏa `Comparable<? super RatedScore>`.
- Phương thức giữ được kiểu trả về `RatedScore`.

```java
// Minh họa hợp lệ với phương thức max linh hoạt nằm trong Tools.
RatedScore selected = Tools.max(a, b);
```

Không thay `super` bằng `extends` theo cảm tính. Với `Comparable<? extends T>`, kiểu cụ thể mà `compareTo` nhận có thể là một kiểu con chưa biết của `T`; không thể đưa tùy ý một `T` vào vị trí đó.

| Giới hạn | Ý nghĩa chính | Kết quả với RatedScore kế thừa Comparable<Score> |
| --- | --- | --- |
| `T extends Comparable<T>` | So sánh qua đúng đối số kiểu `T` | Không thỏa khi chọn `T = RatedScore` |
| `T extends Comparable<? super T>` | Cho phép phép so sánh nhận `T` hoặc kiểu cha | Thỏa với `T = RatedScore` |

Dạng linh hoạt không cho phép so sánh tùy ý hai kiểu không liên quan, chẳng hạn `String` và `Integer`. Nó vẫn cần một lựa chọn `T` thỏa đầy đủ giới hạn và tương thích với cả hai đối số.

## 7. Chương trình đầy đủ

Lưu vào `RecursiveComparableDemo.java`:

```java
import java.util.Objects;

public class RecursiveComparableDemo {
    static <T extends Comparable<T>> T strictMax(T first, T second) {
        Objects.requireNonNull(first);
        Objects.requireNonNull(second);
        return first.compareTo(second) >= 0 ? first : second;
    }

    static <T extends Comparable<? super T>> T max(T first, T second) {
        Objects.requireNonNull(first);
        Objects.requireNonNull(second);
        return first.compareTo(second) >= 0 ? first : second;
    }

    static class Score implements Comparable<Score> {
        private final int points;

        Score(int points) {
            this.points = points;
        }

        int points() {
            return points;
        }

        @Override
        public int compareTo(Score other) {
            Objects.requireNonNull(other);
            return Integer.compare(points, other.points);
        }

        @Override
        public boolean equals(Object other) {
            if (!(other instanceof Score)) {
                return false;
            }
            Score score = (Score) other;
            return points == score.points;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(points);
        }
    }

    static final class RatedScore extends Score {
        private final String label;

        RatedScore(int points, String label) {
            super(points);
            this.label = Objects.requireNonNull(label);
        }

        String label() {
            return label;
        }
    }

    public static void main(String[] args) {
        Integer largest = strictMax(3, 7);
        System.out.println(largest);

        String lastWord = max("apple", "pear");
        System.out.println(lastWord);

        RatedScore low = new RatedScore(10, "An");
        RatedScore high = new RatedScore(20, "Binh");

        RatedScore best = max(low, high);
        System.out.println(best.label());

        Score selectedAsParent = strictMax(low, high);
        System.out.println(selectedAsParent.points());

        RatedScore samePoints = new RatedScore(20, "Chi");
        System.out.println(max(high, samePoints) == high);
        System.out.println(high.compareTo(samePoints) == 0);
        System.out.println(high.equals(samePoints));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 RecursiveComparableDemo.java
java RecursiveComparableDemo
```

Stdout chính xác:

```text
7
pear
Binh
20
true
true
true
```

Giải thích:

1. `Integer` có khả năng so sánh với `Integer`, nên thỏa giới hạn chặt.
2. `String` có thứ tự tự nhiên; `"pear"` đứng sau `"apple"`.
3. Dạng linh hoạt cho phép chọn `T = RatedScore`, giữ kết quả qua kiểu con và gọi `label()`.
4. Dạng chặt vẫn gọi được bằng cách suy luận `T = Score`; biến kết quả có kiểu cha.
5. Khi hai đối số bằng nhau theo thứ tự, dấu `>= 0` khiến phương thức trả về đối số đầu tiên. So sánh tham chiếu ở dòng này chỉ kiểm tra chính sách chọn khi hòa, không thay thế so sánh giá trị.
6. Hai đối tượng có cùng `points` nên `compareTo` trả về `0`.
7. Mô hình ví dụ định nghĩa `equals` và `hashCode` theo cùng giá trị `points`, nên hai điểm số này cũng bằng nhau theo `equals`.

Trong mô hình này, `label` chỉ là thông tin mô tả; nó không tham gia thứ tự hay quan hệ bằng nhau. Đây là quyết định tường minh của ví dụ. Nếu trong bài toán thực tế nhãn hoặc định danh có vai trò phân biệt giá trị, phải thiết kế lại hợp đồng so sánh và bằng nhau cho phù hợp.

Để kiểm tra giới hạn chặt, thử thêm dòng sau vào `main`; nó cố ý không biên dịch:

```java
RatedScore rejected =
        RecursiveComparableDemo.<RatedScore>strictMax(low, high);
```

Dòng này dùng đối số kiểu tường minh để tránh nhầm lẫn với trường hợp trình biên dịch tự chọn `Score`.

## 8. Comparable không tự bảo đảm mọi quy tắc dữ liệu

Giới hạn generic chỉ cho phép trình biên dịch kiểm tra khả năng gọi phương thức với kiểu thích hợp. Nó không tự bảo đảm:

- Thuật toán `compareTo` thật sự bắc cầu và nhất quán.
- Đối số khác `null`.
- Dữ liệu không thay đổi trong lúc đang được sắp xếp.
- Hai đối tượng có kết quả so sánh `0` chắc chắn bằng nhau theo `equals`.

`Comparable` khuyến nghị thứ tự tự nhiên nhất quán với `equals`; nếu không, cần nêu rõ trong hợp đồng lớp. Các cấu trúc có thứ tự như `TreeSet` và `TreeMap` dựa vào phép so sánh để phân biệt phần tử/khóa theo thứ tự, nên khác biệt giữa `compareTo == 0` và `equals` có thể ảnh hưởng hành vi.

Trong chương trình, `Score` được thiết kế để hai cách đánh giá bằng nhau nhất quán. Điều này đến từ phần triển khai, không phải từ dòng `T extends Comparable<T>`.

Nếu trường dùng làm khóa so sánh có thể thay đổi, cần cân nhắc ảnh hưởng khi đối tượng đã nằm trong một cấu trúc dữ liệu có thứ tự. Chọn các trường ổn định thường giúp hợp đồng dễ duy trì hơn.

## 9. Khi nên truyền Comparator thay vì ép Comparable

`Comparable` biểu diễn thứ tự tự nhiên do chính kiểu cung cấp. Không phải lớp nào cũng có một thứ tự tự nhiên duy nhất.

Ví dụ, cùng một bản ghi có thể được xếp theo tên, theo ngày tạo hoặc theo độ ưu tiên. Khi thứ tự là lựa chọn của bên sử dụng, truyền một `Comparator` thường thể hiện đúng yêu cầu hơn:

```java
// Phương thức minh họa; cần import java.util.Comparator và java.util.Objects.
static <T> T maxBy(T first, T second, Comparator<? super T> order) {
    Objects.requireNonNull(first);
    Objects.requireNonNull(second);
    Objects.requireNonNull(order);
    return order.compare(first, second) >= 0 ? first : second;
}
```

`maxBy` không yêu cầu `T` thực hiện `Comparable`, vì khả năng so sánh được cung cấp bằng tham số `order`. Giới hạn `? super T` ở đây cũng phù hợp vì comparator nhận các giá trị `T` làm đầu vào.

Không thêm `Comparable` vào một lớp chỉ để thỏa một hàm tiện ích nếu bài toán chưa có thứ tự tự nhiên rõ ràng. Chọn hợp đồng theo ý nghĩa dữ liệu.

## 10. Những lỗi thường gặp

### Quên đối số kiểu của Comparable trong ý nghĩa hợp đồng

Không chỉ hỏi “kiểu này có Comparable không?”. Hãy hỏi “nó so sánh với kiểu nào?”. `Comparable<Score>` và `Comparable<RatedScore>` không phải cùng một kiểu.

### Viết phép so sánh bằng > cho T

```java
// Minh họa lỗi; không biên dịch.
static <T extends Comparable<T>> T wrong(T first, T second) {
    return first > second ? first : second;
}
```

Giới hạn interface không định nghĩa lại toán tử `>` cho đối tượng `T`. Phải gọi `compareTo`.

### Dùng == 1 để kiểm tra lớn hơn

Hợp đồng chỉ bảo đảm dấu, không bảo đảm mọi kết quả dương là `1`. Dùng `> 0`.

### Cho rằng dạng chặt luôn từ chối mọi lời gọi bằng đối tượng con

Suy luận có thể chọn kiểu cha. Muốn phân tích đúng, xem cả đối số đầu vào, kiểu đích và đối số kiểu tường minh.

### Cho rằng giới hạn đệ quy gây vòng lặp runtime

Giới hạn là thông tin kiểm tra kiểu khi biên dịch. Có đệ quy khi chạy hay không phụ thuộc phần thân các phương thức thực tế.

## 11. Tự kiểm tra

1. Giải thích từng phần của `<T extends Comparable<T>>` mà không dùng cách nói “`T` kế thừa chính nó”.
2. Vì sao `first.compareTo(second)` hợp lệ khi có giới hạn, nhưng không hợp lệ với `<T>` đơn thuần?
3. Với `RatedScore` kế thừa `Score`, trong đó `Score implements Comparable<Score>`, vì sao dạng `Comparable<? super T>` giữ được kiểu kết quả `RatedScore`?
4. So sánh hai lời gọi: `Score s = strictMax(low, high)` và lời gọi có `<RatedScore>` tường minh. Lựa chọn `T` khác nhau thế nào?
5. Đổi `>= 0` thành `> 0` trong `max`. Khi hai điểm bằng nhau, đối tượng nào được trả về?
6. Viết một lớp biểu diễn phiên bản với số major/minor và thứ tự tự nhiên phù hợp. Dùng `Integer.compare`, không dùng phép trừ để so sánh trường.
7. Nếu một lớp cần nhiều thứ tự khác nhau tùy màn hình, vì sao truyền `Comparator` có thể phù hợp hơn một giới hạn `Comparable`?

## Tài liệu đối chiếu

- [Java Language Specification — Type Variables (§4.4)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.4): tham số kiểu và giới hạn.
- [Java API — Comparable<T>](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Comparable.html): hợp đồng `compareTo`, thứ tự tự nhiên và quan hệ với `equals`.
- [Java API — Collections.max](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#max(java.util.Collection)): một API chuẩn sử dụng giới hạn `Comparable<? super T>`.
- [Java API — TreeSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeSet.html): quan hệ giữa thứ tự và hợp đồng của tập hợp.
- [Java API — Comparator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Comparator.html): lựa chọn thứ tự từ bên ngoài kiểu dữ liệu.
