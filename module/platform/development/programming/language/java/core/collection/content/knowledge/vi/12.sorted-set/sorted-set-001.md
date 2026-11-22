# SortedSet và thứ tự tự nhiên hoặc Comparator

## 1. Một tập hợp vừa loại trùng vừa duy trì thứ tự

Giả sử chương trình nhận các mức ưu tiên `7, 2, 9, 2, 5`. Bạn cần mỗi mức xuất hiện một lần và luôn duyệt theo thứ tự tăng dần. Nếu chỉ đưa dữ liệu vào một tập bất kỳ, yêu cầu loại trùng chưa bảo đảm yêu cầu sắp xếp. Nếu chỉ sắp một danh sách, hai lần xuất hiện của số 2 vẫn có thể còn nguyên.

`SortedSet<E>` biểu diễn một tập hợp có quy tắc thứ tự trên các phần tử. Một cách triển khai thông dụng là `TreeSet<E>`. Với thứ tự tự nhiên của `Integer`, ví dụ trên cho `[2, 5, 7, 9]`, bất kể số 7 được thêm trước số 2.

Điểm quan trọng hơn “kết quả in ra có sắp xếp” là **quy tắc so sánh còn quyết định phần tử nào được xem là trùng**. Nếu so sánh hai đối tượng cho kết quả 0, tập sắp xếp xem chúng thuộc cùng một vị trí tương đương. Chọn `Comparator` vì thế là chọn cả trình tự lẫn một phần ý nghĩa của sự duy nhất.

Bài học đi từ hai nguồn tạo thứ tự — thứ tự tự nhiên và `Comparator` — đến ví dụ đối tượng tự định nghĩa, tiêu chí phụ, trường hợp bằng nhau, các phương thức cơ bản và lỗi cần tránh. Mã hoàn chỉnh dùng API có trong Java 17.

Bạn chỉ cần biết biến, lớp, phương thức, kiểu tổng quát như `List<Integer>` và vòng lặp. Các khái niệm `Comparable`, `Comparator` và giá trị trả về của phép so sánh được giải thích trước khi dùng.

## 2. SortedSet là hợp đồng; TreeSet là một cách triển khai

Có thể đọc khai báo:

~~~java
SortedSet<Integer> priorities = new TreeSet<>();
~~~

như sau:

- `SortedSet<Integer>` là kiểu mà phần mã sử dụng nhìn thấy: tập hợp số nguyên có thứ tự và các thao tác liên quan đến thứ tự.
- `new TreeSet<>()` tạo đối tượng cụ thể thực hiện hợp đồng đó.
- `Integer` là kiểu phần tử; `int` được đóng gói thành `Integer` khi cần.

Đoạn trên là khai báo minh họa; cần nhập `java.util.SortedSet` và `java.util.TreeSet` khi đặt vào một chương trình.

`SortedSet` mở rộng `Set`, nên vẫn có `add`, `contains`, `remove`, `size` và khả năng duyệt. Nó bổ sung cách lấy phần tử đầu/cuối, hỏi quy tắc so sánh và tạo các vùng theo thứ tự.

Bức tranh khái niệm:

~~~text
Set
  └─ SortedSet: thêm hợp đồng thứ tự
       └─ NavigableSet: thêm các phép tìm lân cận theo thứ tự
            └─ TreeSet: một lớp triển khai cụ thể
~~~

Sơ đồ mô tả quan hệ kiểu, không phải cấu trúc nút của cây trong bộ nhớ. Các phép tìm lân cận như `floor` hoặc `ceiling` thuộc phạm vi mở rộng; để hiểu thứ tự tự nhiên và `Comparator`, trước hết cần nắm đúng hợp đồng `SortedSet`.

Theo API, thứ tự có thể đến từ bản thân phần tử hoặc từ một `Comparator` được cung cấp khi tạo tập. Bộ duyệt đi theo thứ tự tăng dần **của quy tắc đang áp dụng**. “Tăng dần” ở đây không mặc nhiên có nghĩa số nhỏ đến số lớn trong mọi tập. [Java 17: SortedSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SortedSet.html).

## 3. Thứ tự tự nhiên đến từ Comparable

Thứ tự tự nhiên (natural ordering) là quy tắc so sánh mà kiểu phần tử cung cấp qua `Comparable<T>`, với phương thức:

~~~java
int compareTo(T other);
~~~

Đây là chữ ký rút gọn để đọc ý nghĩa, không phải chương trình độc lập.

Với `a.compareTo(b)`:

| Kết quả | Ý nghĩa theo quy tắc của kiểu |
| --- | --- |
| Nhỏ hơn 0 | `a` đứng trước `b` |
| Bằng 0 | `a` và `b` tương đương về thứ tự |
| Lớn hơn 0 | `a` đứng sau `b` |

Chỉ dấu âm, 0 hoặc dương có ý nghĩa chung. Không viết mã chỉ nhận `-1` và `1`, vì một phép so sánh hợp lệ có thể trả một số âm hoặc dương khác.

Ví dụ, thứ tự tự nhiên của `Integer` là thứ tự số học. `new TreeSet<Integer>()` không cần bạn truyền thêm một hàm để biết số 2 đứng trước số 7.

Với `String`, thứ tự tự nhiên là thứ tự từ điển theo giá trị các đơn vị mã ký tự trong chuỗi. Nó không tự trở thành quy tắc sắp tên tiếng Việt, không tự bỏ qua chữ hoa/thường và không diễn giải chuỗi phiên bản như các thành phần số. Chẳng hạn, việc sắp chuỗi `"1.10"` và `"1.9"` không tương đương việc so sánh hai cặp số `(1, 10)` và `(1, 9)`. [Java 17: String.compareTo](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#compareTo(java.lang.String)).

Một lớp không tự có thứ tự tự nhiên chỉ vì có các trường số hoặc có `toString`. `record` cũng không tự triển khai `Comparable`. Nếu muốn `Version` có thứ tự tự nhiên, phải khai báo và viết quy tắc so sánh thích hợp.

Ví dụ trong chương trình bên dưới so sánh phiên bản theo phần chính trước, phần phụ sau:

~~~text
1.9  đứng trước  1.10  đứng trước  2.0
~~~

Đó là quyết định của mô hình `Version` trong bài; nó không cố diễn giải mọi quy ước phiên bản phần mềm ngoài thực tế.

## 4. Comparator là quy tắc thứ tự được cung cấp từ bên ngoài

Một kiểu dữ liệu có thể cần nhiều cách trình bày. Danh sách thí sinh có thể ưu tiên điểm cao; một màn hình khác có thể ưu tiên tên. Không nên ép mọi yêu cầu đó thành một thứ tự tự nhiên duy nhất của đối tượng.

`Comparator<T>` đóng gói một quy tắc so sánh riêng. Phương thức trọng tâm là:

~~~java
int compare(T left, T right);
~~~

Dấu của kết quả có cùng vai trò với `compareTo`. Sự khác nhau là nơi đặt quy tắc:

| Tiêu chí | Comparable | Comparator |
| --- | --- | --- |
| Quy tắc nằm ở đâu? | Trong kiểu phần tử | Trong đối tượng so sánh bên ngoài |
| Phương thức chính | `a.compareTo(b)` | `rule.compare(a, b)` |
| Tình huống phù hợp | Một thứ tự mặc định rõ nghĩa của kiểu | Thứ tự theo một nhu cầu cụ thể hoặc nhiều cách sắp |
| Khi dùng với TreeSet | Không cần truyền bộ so sánh riêng | Truyền quy tắc vào hàm khởi tạo |

Ví dụ minh họa cho số nguyên:

~~~java
SortedSet<Integer> descending =
        new TreeSet<>(Comparator.reverseOrder());
~~~

Tập này dùng thứ tự ngược với thứ tự tự nhiên. Thêm `7, 2, 9, 5` sẽ duyệt thành `[9, 7, 5, 2]`.

Một `Comparator` được cung cấp sẽ quyết định thứ tự của tập đó; không có bước tự động “nếu comparator thấy bằng thì quay sang compareTo”. Nếu muốn tiêu chí phụ, phải viết hoặc ghép tiêu chí phụ rõ ràng.

Đối tượng không triển khai `Comparable` vẫn có thể nằm trong `TreeSet` nếu `Comparator` cung cấp so sánh hợp lệ cho các phần tử. Đó là lý do `Candidate` trong chương trình không cần một phương thức `compareTo`.

## 5. Hiểu “tăng dần” theo chính Comparator

Khi dùng thứ tự ngược, số 9 đứng trước số 2 vì bộ so sánh đang xem 9 là nhỏ hơn 2 theo thứ tự mà nó định nghĩa. Không có mâu thuẫn giữa hợp đồng duyệt tăng dần và kết quả `[9, 7, 5, 2]`.

Hãy dịch các từ “đầu”, “cuối”, “nhỏ hơn” và “lớn hơn” sang quan hệ của quy tắc hiện tại:

| Tập | Thứ tự duyệt | first() | last() |
| --- | --- | --- | --- |
| Tự nhiên của Integer | `[2, 5, 7, 9]` | `2` | `9` |
| Ngược thứ tự tự nhiên | `[9, 7, 5, 2]` | `9` | `2` |

`first()` không có nghĩa “phần tử được thêm đầu tiên”. `last()` cũng không có nghĩa “phần tử vừa được thêm”. Chúng dựa vào thứ tự của tập tại thời điểm gọi.

Với một tập rỗng, `first()` và `last()` ném `NoSuchElementException`. Chúng không dùng `null` làm giá trị chung báo rỗng. Điều này đặc biệt đáng chú ý khi bạn tự cung cấp một quy tắc cho phép `null`: một tập không rỗng có thể có phần tử đầu là `null`.

Phương thức `comparator()` trả bộ so sánh đang được dùng hoặc `null` nếu tập dùng thứ tự tự nhiên. `comparator() == null` không có nghĩa “không sắp xếp”, cũng không chứng minh tập cho phép phần tử `null`. Hai ý nghĩa của từ `null` nằm ở hai câu hỏi khác nhau.

## 6. So sánh bằng 0 quyết định trùng trong tập sắp xếp

Giả sử mô hình `Candidate` có hai thành phần:

~~~text
name: tên
score: điểm
~~~

Và đầu vào là:

~~~text
An:90
Binh:90
Chi:80
~~~

Nếu quy tắc chỉ so sánh `score`, nó xem `An:90` và `Binh:90` tương đương vì:

~~~text
compare(An:90, Binh:90) = 0
~~~

Một `TreeSet` dùng quy tắc đó chỉ giữ một đại diện cho nhóm điểm 90. Khi thêm `An` trước rồi `Binh`, kết quả của ví dụ là `[Chi:80, An:90]`. Số phần tử bằng 2, không phải 3.

Đây không phải lỗi `TreeSet` quên so sánh tên. Bạn đã cung cấp một quy tắc không dùng tên, và tập dùng đúng quy tắc ấy để xác định sự tương đương.

Hệ quả không chỉ xuất hiện ở `add`. `contains(new Candidate("Unknown", 90))` cũng có thể trả `true` trong tập chỉ so sánh điểm: đã có một đại diện tương đương về thứ tự, dù không có thí sinh tên `Unknown`. Nếu dùng `remove` bằng đối tượng như vậy, bạn có thể xóa đại diện của nhóm điểm đó.

Đây là lý do không xem `Comparator` của tập chỉ như một tùy chọn trình bày. Nó tham gia trực tiếp vào việc tìm và phân biệt phần tử. Với `TreeSet`, không có phép băm bổ sung để phân biệt hai đối tượng sau khi so sánh đã cho 0. [Java 17: TreeSet, so sánh phần tử và hợp đồng Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).

Nếu nghiệp vụ cần giữ mọi thí sinh cùng điểm, “điểm” chưa phải tiêu chí đủ để phân biệt phần tử trong tập. Có thể thêm tiêu chí phù hợp với mô hình, hoặc dùng danh sách được sắp xếp nếu bạn cần giữ mọi bản ghi kể cả bản trùng.

## 7. Ghép tiêu chí: điểm giảm dần, tên tăng dần

Trong mô hình nhỏ của bài, `Candidate` là `record` chỉ gồm `name` và `score`. Phép `equals` mặc định của nó xét cả hai thành phần. Các tên trong ví dụ khác `null`.

Ta chọn thứ tự:

1. Điểm cao đứng trước.
2. Nếu điểm bằng nhau, tên tăng dần.

Quy tắc được viết như sau:

~~~java
Comparator<Candidate> ranking =
        Comparator.comparingInt(Candidate::score).reversed()
                .thenComparing(Candidate::name);
~~~

Đoạn này được dùng nguyên vẹn trong chương trình đầy đủ. `Candidate::score` là tham chiếu phương thức: lấy điểm của một thí sinh. `comparingInt` tạo so sánh theo số nguyên; `reversed` đảo hướng của tiêu chí điểm; `thenComparing` chỉ dùng tên khi tiêu chí trước cho kết quả 0.

Ba thí sinh khi đó được duyệt thành:

~~~text
[An:90, Binh:90, Chi:80]
~~~

`An` và `Binh` cùng điểm nhưng không còn cho kết quả so sánh 0 vì tên khác nhau. Hai đối tượng đều có `name="An"` và `score=90` vẫn cho 0, đúng với phép `equals` của mô hình `record` này.

Không đặt `reversed()` tùy tiện. Biểu thức:

~~~java
Comparator.comparingInt(Candidate::score)
        .thenComparing(Candidate::name)
        .reversed()
~~~

đảo **toàn bộ** thứ tự đã ghép: cả điểm lẫn tên đều đổi hướng. Nó không biểu thị “điểm giảm, tên tăng”. Đây là đoạn minh họa để đối chiếu phạm vi của `reversed`, không phải quy tắc được dùng trong chương trình.

Các hàm ghép bộ so sánh mô tả thứ tự theo từng tiêu chí; đọc từ trái sang phải và xác định chính xác đoạn nào được đảo hướng. [Java 17: Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).

Tên trong ví dụ không thay thế một định danh thí sinh ngoài đời. Nếu hệ thống thực có mã dự thi, yêu cầu duy nhất và phép `equals` cần được thiết kế theo mô hình đó. Không tự thêm một trường bất kỳ làm tiêu chí phụ rồi cho rằng mọi vấn đề nhận diện đã được giải quyết.

## 8. Nhất quán với equals là điều kiện cần kiểm tra

Một thứ tự nhất quán với `equals` nghĩa là, đối với các phần tử trong miền sử dụng:

~~~text
compare(a, b) == 0  khi và chỉ khi  a.equals(b)
~~~

Với thứ tự tự nhiên, thay `compare(a, b)` bằng `a.compareTo(b)`. Dấu bằng 0 ở đây là quan hệ tương đương về thứ tự, không phải phép so sánh tham chiếu `a == b`.

Hợp đồng chung của `Set` được diễn đạt bằng `equals`. Tập sắp xếp lại dùng phép so sánh để xác định tương đương. Khi hai quan hệ không khớp, tập có thể hoạt động xác định theo bộ so sánh mà vẫn không đáp ứng đầy đủ kỳ vọng của hợp đồng `Set`.

Trong chương trình:

- Quy tắc chỉ theo điểm gộp `An:90` và `Binh:90` dù `equals` của record phân biệt chúng. Đây là ví dụ cố ý làm lộ sai lệch.
- Quy tắc điểm rồi tên xét đủ hai thành phần của record, với miền tên khác `null` của ví dụ. Hai đối tượng chỉ so sánh bằng 0 khi chúng bằng nhau theo `equals`.

Đừng sửa bằng cách “không bao giờ trả 0, kể cả cùng đối tượng”. Khi đó bạn phá vỡ chính hợp đồng của phép so sánh. Tập không phải cách lưu nhiều bản trùng bằng một bộ so sánh giả vờ mọi thứ luôn khác nhau.

Một ngoại lệ nổi tiếng trong JDK là `BigDecimal`. `new BigDecimal("1.0")` và `new BigDecimal("1.00")` bằng nhau về giá trị số theo `compareTo` nhưng khác `equals` vì cách biểu diễn có thang đo khác nhau. `TreeSet` theo thứ tự tự nhiên xem chúng là một nhóm tương đương và lần thêm thứ hai trả `false`. API cũng nêu rõ điểm cần lưu ý này khi dùng `BigDecimal` trong tập hoặc ánh xạ sắp xếp. [Java 17: BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).

Không cần học toàn bộ phép tính thập phân để rút ra bài học: không mặc định `compareTo == 0` luôn đồng nghĩa `equals == true` với mọi kiểu có sẵn. Khi chọn kiểu phần tử hoặc một bộ so sánh mới, hãy kiểm tra quy tắc bằng nhau thực tế.

## 9. Bộ so sánh phải hợp lệ trên toàn bộ miền dữ liệu

Một quy tắc thứ tự phải cho kết quả có thể dùng nhất quán, không chỉ đúng với một cặp dữ liệu mẫu.

Các điều kiện quan trọng gồm:

- Đảo hai đối số phải đảo dấu kết quả, với 0 vẫn là 0.
- Quan hệ trước/sau phải có tính bắc cầu: nếu `a` đứng trước `b` và `b` đứng trước `c`, không được để `a` đứng sau `c`.
- Nếu `a` và `b` so sánh bằng 0, quan hệ của chúng với một phần tử thứ ba phải tương thích.

Quy tắc này được mô tả trong hợp đồng `Comparable` và `Comparator`. Đừng dùng một phép so sánh phụ thuộc ngẫu nhiên hoặc thay đổi ý nghĩa giữa hai lời gọi cho cùng dữ liệu. [Java 17: Comparable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html).

Một lỗi thường gặp là so sánh số nguyên bằng phép trừ:

~~~java
// Minh họa cách viết cần tránh khi giá trị có thể tràn số.
Comparator<Integer> unsafe = (a, b) -> a - b;
~~~

Hai toán hạng hợp lệ vẫn có thể tạo hiệu vượt phạm vi `int`, khiến dấu của kết quả sai. Dùng `Integer.compare(a, b)` hoặc `Comparator.naturalOrder()` thay vì tự suy dấu từ phép trừ.

Cũng không dùng một biến trạng thái có thể thay đổi để lặng lẽ đổi quy tắc sau khi đã thêm dữ liệu. Tập không tự tháo và dựng lại cấu trúc mỗi khi biến mà bộ so sánh đang đọc bị đổi.

Cách dễ theo dõi là xây dựng bộ so sánh ổn định, dùng các hàm so sánh chuẩn và kiểm tra những cặp có giá trị biên, bằng tiêu chí đầu, khác tiêu chí phụ. Với mô hình record trong bài, bất biến của dữ liệu giúp tránh việc thứ tự thay đổi ngoài các thao tác của tập.

## 10. Chương trình đầy đủ dùng Java 17

Lưu mã sau thành `SortedSetOrderingDemo.java`. Chương trình gồm các nhóm ví dụ độc lập được in bằng nhãn rõ ràng:

- Số nguyên theo thứ tự tự nhiên và thứ tự ngược.
- `Version` tự cung cấp `Comparable`.
- `Candidate` dùng bộ so sánh chỉ theo điểm và bộ so sánh đầy đủ hơn.
- Vùng `subSet`, việc sao chép và chính sách `null`.
- Các lỗi dự kiến và trường hợp `BigDecimal`.

Các khối `try/catch` chỉ minh họa những lỗi cụ thể được dự đoán; chúng không che giấu lỗi bất kỳ của toàn bộ chương trình.

~~~java
import java.math.BigDecimal;
import java.util.Collection;
import java.util.Comparator;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.SortedSet;
import java.util.TreeSet;

public class SortedSetOrderingDemo {
    record Version(int major, int minor) implements Comparable<Version> {
        @Override
        public int compareTo(Version other) {
            int byMajor = Integer.compare(major, other.major);
            return byMajor != 0 ? byMajor : Integer.compare(minor, other.minor);
        }

        @Override
        public String toString() {
            return major + "." + minor;
        }
    }

    record Candidate(String name, int score) {
        @Override
        public String toString() {
            return name + ":" + score;
        }
    }

    public static void main(String[] args) {
        SortedSet<Integer> natural = new TreeSet<>();
        for (int number : new int[] {7, 2, 9, 2, 5}) {
            System.out.println("add " + number + "=" + natural.add(number));
        }
        System.out.println("natural=" + natural);
        System.out.println("natural comparator is null=" + (natural.comparator() == null));
        System.out.println("natural first/last=" + natural.first() + "/" + natural.last());

        SortedSet<Integer> reverse = new TreeSet<>(Comparator.reverseOrder());
        reverse.addAll(natural);
        System.out.println("reverse=" + reverse);
        System.out.println("reverse comparator is null=" + (reverse.comparator() == null));
        System.out.println("reverse first/last=" + reverse.first() + "/" + reverse.last());
        System.out.println("reverse subSet(9,5)=" + reverse.subSet(9, 5));

        SortedSet<Version> versions = new TreeSet<>();
        versions.addAll(List.of(new Version(1, 10), new Version(2, 0), new Version(1, 9)));
        System.out.println("versions=" + versions);
        System.out.println("version duplicate=" + versions.add(new Version(1, 10)));

        List<Candidate> input = List.of(
                new Candidate("An", 90),
                new Candidate("Binh", 90),
                new Candidate("Chi", 80));
        SortedSet<Candidate> scoreOnly =
                new TreeSet<>(Comparator.comparingInt(Candidate::score));
        scoreOnly.addAll(input);
        System.out.println("score only=" + scoreOnly);
        System.out.println("score only size=" + scoreOnly.size());
        Candidate stranger = new Candidate("Unknown", 90);
        System.out.println("different by equals=" + !input.get(0).equals(stranger));
        System.out.println("score only contains stranger=" + scoreOnly.contains(stranger));

        Comparator<Candidate> ranking =
                Comparator.comparingInt(Candidate::score).reversed()
                        .thenComparing(Candidate::name);
        SortedSet<Candidate> ranked = new TreeSet<>(ranking);
        ranked.addAll(input);
        System.out.println("ranked=" + ranked);
        System.out.println("ranked size=" + ranked.size());
        System.out.println("ranked duplicate=" + ranked.add(new Candidate("An", 90)));
        System.out.println("ranked contains stranger=" + ranked.contains(stranger));

        SortedSet<Integer> middle = natural.subSet(2, 9);
        System.out.println("middle initial=" + middle);
        middle.add(6);
        System.out.println("parent after view add=" + natural);
        natural.remove(5);
        System.out.println("middle after parent remove=" + middle);
        System.out.println("headSet(7)=" + natural.headSet(7));
        System.out.println("tailSet(7)=" + natural.tailSet(7));
        try {
            middle.add(9);
        } catch (IllegalArgumentException exception) {
            System.out.println("outside view=" + exception.getClass().getSimpleName());
        }

        SortedSet<Integer> copySame = new TreeSet<>(reverse);
        Collection<Integer> collectionInput = reverse;
        SortedSet<Integer> copyNatural = new TreeSet<>(collectionInput);
        System.out.println("sorted-set copy=" + copySame);
        System.out.println("collection copy=" + copyNatural);

        SortedSet<Integer> nullable =
                new TreeSet<>(Comparator.nullsFirst(Comparator.naturalOrder()));
        nullable.addAll(java.util.Arrays.asList(5, null, 2, null));
        System.out.println("nullable=" + nullable);
        System.out.println("nullable first=" + nullable.first());
        try {
            natural.add(null);
        } catch (NullPointerException exception) {
            System.out.println("natural null=" + exception.getClass().getSimpleName());
        }

        SortedSet<Candidate> missingRule = new TreeSet<>();
        try {
            missingRule.add(new Candidate("An", 90));
        } catch (ClassCastException exception) {
            System.out.println("missing ordering=" + exception.getClass().getSimpleName());
        }
        try {
            new TreeSet<Integer>().first();
        } catch (NoSuchElementException exception) {
            System.out.println("empty first=" + exception.getClass().getSimpleName());
        }

        BigDecimal one = new BigDecimal("1.0");
        BigDecimal sameNumber = new BigDecimal("1.00");
        SortedSet<BigDecimal> decimals = new TreeSet<>();
        decimals.add(one);
        System.out.println("decimal equals=" + one.equals(sameNumber));
        System.out.println("decimal compare=" + one.compareTo(sameNumber));
        System.out.println("decimal second add=" + decimals.add(sameNumber));
        System.out.println("decimal size=" + decimals.size());
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 SortedSetOrderingDemo.java
java SortedSetOrderingDemo
~~~

Dùng JDK 17 trở lên. Tùy chọn `--release 17` kiểm tra mã và API theo Java 17; tên tệp khớp với lớp `public`.

Kết quả chuẩn:

~~~text
add 7=true
add 2=true
add 9=true
add 2=false
add 5=true
natural=[2, 5, 7, 9]
natural comparator is null=true
natural first/last=2/9
reverse=[9, 7, 5, 2]
reverse comparator is null=false
reverse first/last=9/2
reverse subSet(9,5)=[9, 7]
versions=[1.9, 1.10, 2.0]
version duplicate=false
score only=[Chi:80, An:90]
score only size=2
different by equals=true
score only contains stranger=true
ranked=[An:90, Binh:90, Chi:80]
ranked size=3
ranked duplicate=false
ranked contains stranger=false
middle initial=[2, 5, 7]
parent after view add=[2, 5, 6, 7, 9]
middle after parent remove=[2, 6, 7]
headSet(7)=[2, 6]
tailSet(7)=[7, 9]
outside view=IllegalArgumentException
sorted-set copy=[9, 7, 5, 2]
collection copy=[2, 5, 7, 9]
nullable=[null, 2, 5]
nullable first=null
natural null=NullPointerException
missing ordering=ClassCastException
empty first=NoSuchElementException
decimal equals=false
decimal compare=0
decimal second add=false
decimal size=1
~~~

## 11. Đọc bằng chứng từ chương trình

### 11.1. Vị trí phụ thuộc quy tắc, không phụ thuộc thứ tự thêm

Số 7 được thêm trước số 2 nhưng `natural` vẫn duyệt `[2, 5, 7, 9]`. Lần thêm số 2 thứ hai trả `false` vì số 2 tương đương theo thứ tự tự nhiên đã có.

`natural comparator is null=true` xác nhận không có bộ so sánh tường minh. Nó không biểu thị tập thiếu thứ tự.

Khi cùng dữ liệu được đưa vào `reverse`, kết quả là `[9, 7, 5, 2]`. `first/last` đổi thành `9/2` vì hai phương thức đọc hai đầu của quy tắc hiện tại.

### 11.2. Comparable và Comparator giải quyết hai cách cung cấp quy tắc

`Version` triển khai `Comparable<Version>`, nên `new TreeSet<Version>()` dùng được thứ tự tự nhiên do lớp cung cấp. So sánh phần chính trước, phần phụ sau cho `[1.9, 1.10, 2.0]`.

`Candidate` không triển khai `Comparable`. Hai tập chứa thí sinh vẫn hoạt động khi nhận `Comparator`. Nhưng `missingRule` không nhận bộ so sánh và cũng không có thứ tự tự nhiên từ phần tử, nên thêm thí sinh dẫn đến `ClassCastException`.

Việc viết được `new TreeSet<Candidate>()` ở thời điểm biên dịch không tự tạo ra `compareTo`. Kiểu tổng quát của `TreeSet` không bắt bạn khai báo `E extends Comparable<E>`, vì còn phải hỗ trợ trường hợp có `Comparator`. Bạn vẫn có trách nhiệm cung cấp một trong hai con đường so sánh hợp lệ.

### 11.3. Bộ so sánh chỉ theo điểm gây hệ quả đến truy vấn

`score only size=2` cho thấy đã có một thí sinh không được thêm như phần tử riêng. `different by equals=true` nhưng `score only contains stranger=true` cho thấy phép tìm của tập đang dùng quan hệ tương đương theo điểm.

Với `ranking` gồm điểm và tên, `ranked size=3` giữ cả ba giá trị record khác nhau trong mẫu. `ranked contains stranger=false` vì tên `Unknown` không khớp bất kỳ đại diện nào khi dùng đủ tiêu chí.

Nhìn vào `size` và `contains` như vậy giúp phát hiện sai mô hình trước khi chỉ tập trung vào việc chuỗi in ra có vẻ “đúng thứ tự”.

### 11.4. Chính sách null cần được chỉ định ở quy tắc

Tập `nullable` nhận `Comparator.nullsFirst(Comparator.naturalOrder())`, nên `null` được xếp trước các số. Hai lần thêm `null` vẫn tạo một thành viên, cho `[null, 2, 5]`.

`nullable first=null` là phần tử thực, không phải dấu hiệu tập rỗng. Trái lại, tập số theo thứ tự tự nhiên không nhận `null` và ví dụ in tên lỗi `NullPointerException`.

### 11.5. Bằng số học và bằng đối tượng có thể khác

`decimal compare=0` đi cùng `decimal equals=false`. Lần thêm số thập phân thứ hai trả `false` và kích thước bằng 1. Tập dùng đúng quan hệ thứ tự của `BigDecimal`, không chuyển sang `equals` để thử phân biệt thêm.

Ví dụ này có chủ đích làm rõ sự không nhất quán giữa hai quan hệ; không phải khuyến nghị bỏ qua khác biệt biểu diễn khi nó quan trọng với dữ liệu của bạn.

## 12. first, last và các vùng theo thứ tự

Ngoài duyệt, `SortedSet` có những phép cơ bản sau:

| Phương thức | Ý nghĩa theo thứ tự hiện tại |
| --- | --- |
| `comparator()` | Trả quy tắc tường minh, hoặc `null` nếu dùng thứ tự tự nhiên |
| `first()` | Phần tử đầu |
| `last()` | Phần tử cuối |
| `subSet(from, to)` | Vùng từ `from`, có tính `from`, đến trước `to` |
| `headSet(to)` | Vùng trước `to`, không tính `to` |
| `tailSet(from)` | Vùng từ `from` trở đi, có tính `from` |

Các phương thức lấy vùng của `SortedSet` trong bảng dùng những quy tắc biên cố định. Những biến thể cho phép chọn tính/không tính biên qua tham số `boolean` thuộc `NavigableSet`, không phải chữ ký hai đối số của `SortedSet.subSet`.

Với thứ tự tự nhiên và dữ liệu `[2, 5, 7, 9]`:

~~~text
subSet(2, 9) → [2, 5, 7]
headSet(7)   → [2, 5]
tailSet(7)   → [7, 9]
~~~

Giá trị biên không bắt buộc phải đang có trong tập. Chúng biểu diễn giới hạn của vùng theo phép so sánh. Chẳng hạn, trên tập ban đầu, `subSet(3, 8)` sẽ chọn các phần tử 5 và 7 dù không có 3 hay 8.

Với thứ tự ngược `[9, 7, 5, 2]`, chương trình dùng `subSet(9, 5)` và nhận `[9, 7]`. Số 9 là đầu vùng theo thứ tự của bộ so sánh; số 5 là biên cuối bị loại. Đừng đổi thành `subSet(5, 9)` chỉ vì 5 nhỏ hơn 9 về số học: hai biên phải hợp lệ theo chính thứ tự của tập.

Nếu hai biên bằng nhau theo so sánh, `subSet(from, to)` là vùng rỗng. Nếu biên đầu đứng sau biên cuối theo quy tắc đang dùng, lời gọi không biểu diễn một vùng hợp lệ.

## 13. Các vùng là khung nhìn liên kết với tập gốc

`subSet` không tạo một bộ dữ liệu độc lập. Nó trả một khung nhìn (view) được tập gốc hậu thuẫn. Chương trình cho bằng chứng hai chiều:

~~~text
natural ban đầu: [2, 5, 7, 9]
middle:          subSet(2, 9) = [2, 5, 7]

middle.add(6)
natural:         [2, 5, 6, 7, 9]

natural.remove(5)
middle:          [2, 6, 7]
~~~

Thêm qua `middle` cập nhật tập gốc. Xóa phần tử thuộc vùng qua tập gốc làm phần tử ấy biến mất khi nhìn qua `middle`.

Khung nhìn vẫn bị ràng buộc bởi biên đã chọn. `middle.add(9)` không hợp lệ vì 9 là biên cuối loại trừ. Nó ném `IllegalArgumentException`, dù tập gốc có thể chứa 9 một cách hợp lệ.

Biên là điều kiện nhận phần tử của khung nhìn, không chỉ là một bộ lọc được dùng một lần lúc tạo biến. Sau khi có khung nhìn, thêm một phần tử phù hợp vào tập gốc cũng có thể làm phần tử đó xuất hiện qua khung nhìn.

Nếu cần một ảnh chụp độc lập, có thể tạo tập mới từ khung nhìn với lựa chọn quy tắc phù hợp. Việc sao chép tập hợp tạo độc lập về thành viên của cấu trúc; nó không tự nhân bản sâu từng đối tượng phần tử.

Cẩn thận khi truyền vùng cho hàm khác: nếu hàm xóa hoặc làm rỗng khung nhìn, dữ liệu tương ứng của tập gốc cũng bị ảnh hưởng. Khi chỉ cần đọc, hợp đồng của hàm nên diễn đạt rõ điều đó thay vì để người gọi tưởng rằng đã nhận bản sao.

## 14. Sao chép có thể giữ hoặc đổi thứ tự tùy hàm khởi tạo

`TreeSet` có nhiều hàm khởi tạo. Hai chữ ký dễ bị đọc như nhau là:

~~~java
new TreeSet<>(aSortedSet);
new TreeSet<>(aCollection);
~~~

Chúng là mẫu khai báo để so sánh, với `aSortedSet` mang kiểu `SortedSet` và `aCollection` mang kiểu `Collection`.

Hàm nhận `SortedSet` giữ quy tắc thứ tự của nguồn. Hàm nhận `Collection` tạo tập theo thứ tự tự nhiên của phần tử. Đó là hai hợp đồng khác nhau, dù đối tượng nguồn thực tế có thể là cùng một `TreeSet`. [Java 17: các hàm khởi tạo TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html#%3Cinit%3E(java.util.SortedSet)).

Chương trình dùng:

~~~java
SortedSet<Integer> copySame = new TreeSet<>(reverse);
Collection<Integer> collectionInput = reverse;
SortedSet<Integer> copyNatural = new TreeSet<>(collectionInput);
~~~

`reverse` có kiểu khai báo `SortedSet<Integer>`, nên lời gọi đầu chọn hàm giữ thứ tự nguồn. `collectionInput` có kiểu khai báo `Collection<Integer>`, nên lời gọi sau chọn hàm tạo theo thứ tự tự nhiên.

Vì vậy, cùng thành viên được sao chép thành:

~~~text
sorted-set copy=[9, 7, 5, 2]
collection copy=[2, 5, 7, 9]
~~~

Điểm cần hiểu là lựa chọn hàm khởi tạo có nhiều chữ ký dựa trên thông tin kiểu khi biên dịch. Không suy rằng lớp thực tế của nguồn tự buộc mọi lời gọi sao chép đều giữ bộ so sánh.

Với đối tượng không có thứ tự tự nhiên, nhầm sang hàm nhận `Collection` còn có thể gây lỗi thay vì chỉ đổi trình tự. Khi quy tắc thứ tự là yêu cầu quan trọng, hãy truyền quy tắc rõ ràng hoặc giữ đúng kiểu nguồn cần thiết.

## 15. null, khả năng so sánh và dữ liệu có thể thay đổi

### 15.1. Chính sách null là một phần của thứ tự

Thứ tự tự nhiên của ví dụ không nhận `null`. Nếu cần hỗ trợ nó, một quy tắc như `Comparator.nullsFirst(Comparator.naturalOrder())` có thể định nghĩa `null` đứng trước phần tử khác. `nullsLast` diễn đạt lựa chọn ở cuối.

Điều này không có nghĩa mọi `Comparator` đều tự nhận `null`. Một bộ so sánh gọi `candidate.score()` sẽ lỗi nếu đối số `candidate` là `null` mà không có lớp bao xử lý phù hợp.

Cũng tách hai trường hợp: bản thân phần tử là `null` và một trường bên trong phần tử là `null`. Bọc bộ so sánh phần tử bằng `nullsFirst` không tự sửa mọi phép so sánh tên có giá trị `null` bên trong một đối tượng khác `null`. Phải định nghĩa chính sách ở đúng cấp dữ liệu.

### 15.2. Các phần tử phải so sánh được với nhau

Một tập theo thứ tự tự nhiên không chỉ yêu cầu “mỗi đối tượng có một phương thức tên `compareTo`”. Các phần tử trong tập phải so sánh được với nhau theo hợp đồng kiểu.

Sử dụng kiểu tổng quát đúng giúp ngăn nhiều trường hợp trộn dữ liệu sai. Đừng dùng kiểu thô để nhét cả `String` lẫn `Integer` vào cùng một tập rồi mong có thứ tự chung chỉ vì cả hai đều triển khai `Comparable` theo cách riêng.

Với `Comparator`, quy tắc phải chấp nhận mọi phần tử hợp lệ của miền dữ liệu bạn đưa vào. Nếu chỉ xử lý một số lớp con hoặc giả định một trường luôn có giá trị trong khi dữ liệu không bảo đảm, lỗi có thể xảy ra lúc thêm, tìm hoặc tạo vùng.

### 15.3. Đừng sửa khóa sắp xếp khi phần tử còn trong tập

Giả sử cây đang được tổ chức theo `score` của một đối tượng có thể sửa. Sau khi thêm đối tượng với điểm 50, bạn đổi trực tiếp trường đó thành 95. `TreeSet` không nhận một lời gọi `add/remove` để biết phải đặt lại phần tử vào đâu.

Kết quả có thể làm thứ tự quan sát và việc tìm kiếm không còn phù hợp với cấu trúc đã xây dựng. Tương tự, thay đổi một biến mà `Comparator` đang đọc cũng có thể làm quy tắc đổi ngầm.

Thiết kế đơn giản là dùng giá trị bất biến cho dữ liệu tham gia so sánh. Nếu phải cập nhật, thực hiện quy trình xóa trong trạng thái cũ rồi thêm giá trị mới dưới một hợp đồng rõ ràng; đừng sửa trước rồi giả định xóa chắc chắn còn tìm đúng vị trí. Hai kiểu record của chương trình giúp giữ ổn định dữ liệu dùng cho thứ tự.

## 16. Chi phí thuộc về cách triển khai, không phải chỉ tên interface

`SortedSet` là hợp đồng hành vi, không phải lời hứa mọi cách triển khai đều dùng cùng thuật toán. Với `TreeSet`, API công bố chi phí `O(log n)` cho `add`, `remove` và `contains`, trong đó `n` là số phần tử. Đó là cam kết của lớp đang dùng trong bài.

Chi phí của chính phép so sánh vẫn quan trọng. So sánh một số nguyên khác với so sánh nhiều trường chuỗi dài. Bộ so sánh gọi thao tác I/O hoặc đọc dữ liệu thay đổi liên tục cũng không phù hợp với một quy tắc thứ tự đơn giản, ổn định.

Đừng mô tả hoạt động của `TreeSet` như “mỗi lần thêm đều sắp xếp lại toàn bộ một danh sách”. Lớp duy trì cấu trúc phù hợp với thứ tự để tìm vị trí và thực hiện các thao tác trên tập. Bài học không cần dựa vào hình dạng nút cụ thể để sử dụng đúng API.

Nếu chỉ cần giữ dữ liệu rồi sắp một lần để hiển thị, một danh sách được sắp xếp có thể phù hợp hơn về ý nghĩa, nhất là khi cần giữ nhiều phần tử cùng khóa sắp xếp. Nếu cần một tập duy nhất luôn có thứ tự và các vùng theo thứ tự trong suốt quá trình cập nhật, `SortedSet` diễn đạt yêu cầu đó trực tiếp hơn.

Dữ liệu được sắp xếp không tự tạo ra tính an toàn khi nhiều luồng cùng sửa. `TreeSet` không được đồng bộ hóa sẵn. Đây là quyết định độc lập với việc dùng `Comparable` hay `Comparator`; chương trình của bài chỉ dùng một luồng.

## 17. Các lỗi thường gặp và cách nhận ra

| Lỗi suy luận | Dấu hiệu hoặc cách sửa |
| --- | --- |
| “TreeSet giữ thứ tự thêm” | Chèn 7 rồi 2 vẫn duyệt 2 trước; phân biệt thứ tự chèn với thứ tự so sánh |
| “Comparator chỉ làm đẹp kết quả in” | Kiểm tra thêm, tìm và loại trùng bằng những đối tượng khác nhau nhưng cùng khóa so sánh |
| “Bằng điểm thì vẫn giữ mọi người” | Nếu chỉ so sánh điểm, phép so sánh trả 0; bổ sung mô hình phân biệt phù hợp hoặc dùng danh sách |
| “Sau khi so sánh 0, TreeSet sẽ xét equals” | Không có bước phân biệt bổ sung đó |
| “compare phải trả đúng -1 hoặc 1” | Kiểm tra dấu của kết quả, không kiểm tra một độ lớn cố định |
| “Lấy hiệu hai số luôn là so sánh đúng” | Có nguy cơ tràn số; dùng `Integer.compare` hoặc hàm chuẩn |
| “first luôn là số nhỏ nhất về số học” | Đọc quy tắc hiện tại; với thứ tự ngược, first là số lớn nhất trong ví dụ |
| “comparator() trả null tức là không có thứ tự” | `null` ở đây biểu thị dùng thứ tự tự nhiên |
| “subSet là bản sao” | Thử thay đổi qua vùng và quan sát tập gốc |
| “TreeSet sao chép luôn giữ comparator” | Kiểm tra chữ ký hàm khởi tạo và kiểu khai báo của nguồn |
| “record tự biết cách sắp xếp” | Record có phép bằng nhau mặc định, không tự có `Comparable` |
| “Đổi trường sắp xếp thì cây tự cập nhật” | Dùng dữ liệu bất biến hoặc quy trình cập nhật qua cấu trúc |
| “Mọi lớp Comparable đều nhất quán với equals” | `BigDecimal` là phản ví dụ cần biết |
| “Set đã sắp xếp thì phù hợp mọi bảng xếp hạng” | Phải kiểm tra yêu cầu giữ nhiều bản ghi có cùng khóa và quy tắc duy nhất |

Khi kết quả thiếu phần tử, hãy in hoặc kiểm tra `compare(a, b)` của hai dữ liệu tưởng là khác nhau. Khi kết quả sai hướng, hãy kiểm tra phạm vi `reversed`. Khi truy vấn vùng bất ngờ, hãy đọc hai biên theo chính bộ so sánh thay vì trực giác số học.

## 18. Thực hành có lời giải

### Bài 1: thứ tự tự nhiên

Thêm lần lượt `8, 3, 8, 1, 5` vào một `TreeSet<Integer>` không truyền `Comparator`. Tập cuối và kết quả lần thêm số 8 thứ hai là gì?

**Lời giải:** Tập cuối là `[1, 3, 5, 8]`. Lần thêm số 8 thứ hai trả `false`. Thứ tự chèn không quyết định trình tự duyệt; lần xuất hiện trùng không tạo thành viên mới.

### Bài 2: đảo quy tắc

Dùng cùng dữ liệu nhưng tạo tập với `Comparator.reverseOrder()`. `first`, `last` và `headSet(5)` là gì?

**Lời giải:** Tập là `[8, 5, 3, 1]`. `first()` bằng 8, `last()` bằng 1. `headSet(5)` chứa phần đứng trước 5 theo quy tắc ngược, nên là `[8]`. Không tính biên 5.

### Bài 3: thiếu tiêu chí phân biệt

Bạn có `Candidate("An", 90)` và `Candidate("Binh", 90)`. Comparator chỉ so sánh điểm. Có thể dùng tập này để giữ đầy đủ danh sách thí sinh không?

**Lời giải:** Không nếu hai thí sinh đó phải là hai thành viên khác nhau. Phép so sánh trả 0 nên tập chỉ giữ một đại diện cho điểm 90. Cần xác định quy tắc duy nhất, thêm tiêu chí tương thích với mô hình hoặc chọn danh sách nếu muốn giữ mọi bản ghi.

### Bài 4: phạm vi reversed

Hai biểu thức “điểm giảm rồi tên tăng” và “điểm tăng rồi tên tăng, cuối cùng đảo toàn bộ” có cùng thứ tự không?

**Lời giải:** Không. Biểu thức thứ nhất chỉ đảo tiêu chí điểm trước khi ghép tên. Biểu thức thứ hai đảo cả hai tiêu chí đã ghép, làm tên cũng giảm khi điểm bằng nhau. Dùng hai thí sinh cùng điểm và tên khác nhau để kiểm tra sự khác biệt.

### Bài 5: khung nhìn theo vùng

Tập tự nhiên là `[1, 3, 5, 7]`. Tạo `view = set.subSet(2, 7)`, rồi gọi `view.remove(3)`. Sau đó tập gốc và vùng là gì? Có thể `view.add(7)` không?

**Lời giải:** Ban đầu vùng là `[3, 5]`. Xóa 3 qua vùng làm tập gốc thành `[1, 5, 7]` và vùng thành `[5]`. Không thêm 7 qua vùng vì biên cuối bị loại; lời gọi ném `IllegalArgumentException`. Việc tập gốc có 7 không nới giới hạn của vùng.

### Bài 6: record không có Comparable

Một record mới chứa `int id` và `String title`. Bạn tạo `new TreeSet<ThatRecord>()` không truyền bộ so sánh. Vì record có `equals`, `hashCode` và `toString`, nó có tự dùng được thứ tự tự nhiên không?

**Lời giải:** Không. Các phương thức đó không tạo `compareTo`. Cần để kiểu triển khai `Comparable` với quy tắc thích hợp hoặc truyền `Comparator` vào tập.

### Bài 7: comparator() và null

Một tập số có `comparator() == null`. Có thể suy rằng nó chưa được sắp xếp hoặc cho phép thêm phần tử `null` không?

**Lời giải:** Không. Giá trị trả về nói rằng tập dùng thứ tự tự nhiên. Chính sách với phần tử `null` là câu hỏi khác; `TreeSet<Integer>` theo thứ tự tự nhiên trong bài từ chối `null`.

### Bài 8: compareTo khác equals

Hai số `BigDecimal("2.0")` và `BigDecimal("2.00")` cho `compareTo` bằng 0 nhưng `equals` bằng `false`. Sau khi thêm cả hai vào `TreeSet` tự nhiên, có hai phần tử không?

**Lời giải:** Không. Phần tử thứ hai tương đương theo thứ tự nên không được thêm thành viên riêng. Nếu khác biệt biểu diễn quan trọng, cần mô hình và quy tắc lưu trữ phù hợp; không mặc định tập theo thứ tự tự nhiên giữ được cả hai.

### Bài 9: tiêu chí tự nhiên của Version

Với `Version` trong chương trình, thêm `2.3, 1.20, 2.1, 1.4`. Thứ tự nào xuất hiện?

**Lời giải:** `[1.4, 1.20, 2.1, 2.3]`. So sánh phần chính trước; chỉ khi phần chính bằng nhau mới so sánh phần phụ dưới dạng số. Không dùng chuỗi hiển thị để suy thứ tự của record.

## 19. Những câu hỏi cần trả lời trước khi chọn quy tắc

Trước khi đưa một kiểu dữ liệu mới vào `SortedSet`, hãy xác định:

- Thứ tự tự nhiên của kiểu có đúng yêu cầu không, hay đây là quy tắc riêng nên dùng `Comparator`?
- Hai đối tượng nào được phép so sánh bằng 0? Chúng có đồng thời bằng nhau theo `equals` không?
- Có những phần tử khác nhau cần giữ dù cùng điểm, cùng tên hoặc cùng thời điểm không?
- Tất cả phần tử và các giá trị biên có so sánh được với nhau không?
- Có cho phép `null` ở cấp phần tử hoặc ở từng trường dùng để so sánh không?
- Dữ liệu hoặc trạng thái mà quy tắc đang đọc có thể thay đổi khi phần tử còn trong tập không?
- Khi dùng `first`, `last` và các vùng, bạn đã đọc “trước/sau” theo đúng bộ so sánh chưa?
- Khi sao chép, bạn cần giữ quy tắc nguồn hay chủ động tạo một thứ tự khác?

Sau khi xác định quy tắc, hãy thử ít nhất một cặp bằng khóa chính nhưng khác khóa phụ. Cặp này thường làm lộ rõ nhất sự khác nhau giữa “sắp xếp bản ghi” và “quyết định bản ghi nào là cùng một thành viên”.
