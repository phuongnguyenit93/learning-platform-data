# Nhất quán giữa Comparator và equals

## 1. Vì sao cần kiểm tra cả Comparator và equals

Trong `TreeSet`, kết quả `compare(a, b) == 0` quyết định hai đầu vào có thuộc cùng nhóm thành viên. Trong hợp đồng chung của `Set`, phép `equals` lại định nghĩa giá trị nào là trùng. Hai quan hệ có thể cho kết quả khác nhau, ngay cả khi từng quan hệ riêng lẻ được định nghĩa rõ ràng.

Ví dụ, `Comparator.comparingInt(String::length)` xem `"cat"` và `"dog"` là tương đương về độ dài, trong khi `String.equals` phân biệt chúng. `TreeSet` theo độ dài chỉ giữ một đại diện. Còn một hướng sai lệch khác khó thấy hơn: hai đối tượng bằng nhau theo `equals` vẫn có thể được bộ so sánh đặt vào hai vị trí khác nhau.

Bài này kiểm tra **cả hai chiều** của điều kiện nhất quán, nhất là với kiểu dữ liệu định danh bằng mã nhưng hiển thị theo nhãn. Ta cũng kiểm tra hệ quả đối với `Set.equals`, rồi thiết kế quy tắc đúng với mô hình. Cần biết `Set`, `Comparator` và `equals`; không cần biết chi tiết cấu trúc nút cây.

## 2. Ba biểu thức giống nhau về tên nhưng khác ý nghĩa

Trước hết, phân biệt:

| Biểu thức | Câu hỏi được trả lời |
| --- | --- |
| `a == b` | Hai biến tham chiếu có trỏ đến cùng đối tượng không? |
| `a.equals(b)` | Hai phần tử có bằng nhau theo quy tắc của kiểu dữ liệu không? |
| `rule.compare(a, b)` | `a` đứng trước, tương đương hay đứng sau `b` theo quy tắc thứ tự? |

Đối với phép `compare`, chỉ dấu của kết quả có ý nghĩa chung:

~~~text
kết quả < 0 : a đứng trước b
kết quả = 0 : a và b tương đương về thứ tự
kết quả > 0 : a đứng sau b
~~~

“Bằng nhau” trong tiêu đề nói về **`equals` của phần tử**, không phải việc so sánh hai đối tượng `Comparator` với nhau. Interface `Comparator` cũng có phương thức `equals(Object)`, nhưng `rule1.equals(rule2)` là một câu hỏi riêng về hai bộ so sánh. Ghi đè phương thức ấy không phải cách làm `compare(a, b)` khớp với `a.equals(b)`.

Tham chiếu khác nhau vẫn có thể biểu diễn hai giá trị bằng nhau. Chẳng hạn, hai đối tượng thành viên cùng mã định danh có thể được mô hình xem là cùng người. Ngược lại, hai từ cùng độ dài vẫn có thể là hai giá trị chuỗi khác nhau.

Vì vậy, đừng dùng `==` thay cho `equals` khi kiểm tra tính nhất quán. Cũng đừng xem kết quả 0 của `compare` như khoảng cách bằng số giữa hai đối tượng: đó là quan hệ tương đương do quy tắc thứ tự định nghĩa.

## 3. Điều kiện “khi và chỉ khi” gồm hai chiều

Một `Comparator` nhất quán với `equals` trên miền phần tử đang xét khi:

~~~text
(rule.compare(a, b) == 0) == a.equals(b)
~~~

đúng cho mọi cặp phần tử hợp lệ `a, b` khác `null`. Nếu miền cho phép `null`, có thể diễn đạt phép bằng nhau bằng `Objects.equals(a, b)` và vẫn phải có bộ so sánh xử lý được các giá trị ấy.

Từ “mọi” rất quan trọng: không chỉ một cặp đầu tiên hoặc vài phần tử hiện có trong tập. Quy tắc cần phù hợp với miền dữ liệu mà chương trình cho phép đưa vào và truy vấn.

Điều kiện có hai chiều:

1. Nếu so sánh bằng 0 thì hai phần tử phải bằng nhau theo `equals`.
2. Nếu hai phần tử bằng nhau theo `equals` thì phép so sánh phải bằng 0.

Bảng bốn trường hợp giúp đọc chính xác:

| `a.equals(b)` | `compare(a, b) == 0` | Kết luận về cặp này |
| --- | --- | --- |
| `true` | `true` | Hai quan hệ khớp |
| `false` | `false` | Hai quan hệ khớp |
| `false` | `true` | Bộ so sánh gom hai giá trị mà equals phân biệt |
| `true` | `false` | Bộ so sánh tách hai giá trị mà equals xem là một |

Không yêu cầu kết quả `compare` phải bằng `hashCode(a) - hashCode(b)`. Không yêu cầu `equals` trả về vị trí hoặc hướng sắp xếp. Hai cơ chế có nhiệm vụ khác nhau; phần cần khớp là ranh giới giữa “tương đương” và “khác nhau”. [Java 17: Comparator, định nghĩa nhất quán với equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).

## 4. Vì sao Set cần điều kiện này?

Hợp đồng chung của `Set` không cho phép giữ đồng thời hai phần tử bằng nhau theo `equals`. Các phép thêm, phép bằng nhau của tập và mã băm của tập cũng liên hệ với cách nhận diện đó. [Java 17: Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

`TreeSet` lại tìm và phân biệt phần tử bằng thứ tự tự nhiên hoặc `Comparator` được chọn khi tạo tập. Khi phép so sánh cho 0, nó xem như đã tìm thấy một thành viên tương đương. Nó không tự gọi thêm `equals` để tách hai đối tượng mà `Comparator` vừa gom lại.

Có thể hình dung hai cách chia dữ liệu thành nhóm:

~~~text
Theo equals:
  [cat] [dog] [owl]

Theo Comparator chỉ xét độ dài:
  [cat, dog, owl]
~~~

Mỗi dấu ngoặc biểu diễn một nhóm được xem là cùng giá trị theo quan hệ tương ứng. Trong tập sắp xếp theo độ dài, cả ba từ thuộc cùng một nhóm tương đương về thứ tự. Tập giữ một đại diện cho nhóm đó.

Nếu hai cách chia nhóm trùng nhau, tập sắp xếp có thể vừa duy trì thứ tự vừa đáp ứng ý nghĩa duy nhất của `Set`. Nếu chúng khác nhau, “không trùng” theo cây không còn đồng nghĩa “không trùng” theo `equals`.

Một bộ so sánh hợp lệ nhưng không nhất quán với `equals` vẫn có thể tạo hành vi xác định trong `TreeSet`. Tuy nhiên, tập đó không tuân thủ đầy đủ hợp đồng chung của `Set`. Đây là vấn đề hợp đồng dữ liệu, không phải ngẫu nhiên mất phần tử do cây hỏng. [Java 17: TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).

## 5. Hướng sai lệch thứ nhất: khác theo equals nhưng compare bằng 0

Với `Comparator.comparingInt(String::length)`, ba từ `"cat"`, `"dog"`, `"owl"` là ba giá trị khác nhau theo `String.equals` nhưng cùng một nhóm so sánh vì đều dài ba ký tự:

~~~text
"cat".equals("dog") = false
byLength.compare("cat", "dog") = 0
~~~

Nếu thêm `"cat"` rồi `"dog"` vào `TreeSet` dùng bộ so sánh ấy, lần thêm sau trả `false` và tập chỉ giữ `"cat"`. `contains("owl")` vẫn trả `true`, còn `remove("owl")` có thể xóa đại diện `"cat"`. Các phép tìm/xóa đều dùng cùng quan hệ so sánh; gọi `contains` trước `add` không giải quyết được sai lệch.

Điểm cần kiểm tra là **ý nghĩa định danh**: nếu chỉ muốn lưu những độ dài xuất hiện, tập các số nguyên độ dài có thể biểu đạt rõ hơn. Nếu muốn lưu mọi từ khác nội dung, phải bổ sung tiêu chí phân biệt tương ứng với `String.equals`. Hướng sai lệch thứ hai, nơi `equals` coi hai phần tử là một nhưng comparator tách chúng ra, đòi hỏi xem xét kỹ hơn mô hình đối tượng.

## 6. Khi nào thêm tiêu chí phụ sửa được vấn đề?

Với `String`, bạn có thể sắp theo độ dài trước, rồi theo toàn bộ nội dung chuỗi khi độ dài bằng nhau:

~~~java
Comparator<String> lengthThenText =
        byLength.thenComparing(Comparator.naturalOrder());
~~~

Lúc này `"cat"` và `"dog"` cùng độ dài nhưng được phân biệt bằng nội dung. Chỉ hai chuỗi có cùng nội dung mới còn cho kết quả 0 ở cả hai tiêu chí.

Dữ liệu `dog, a, cat, cat` tạo tập:

~~~text
[a, cat, dog]
~~~

Thứ tự độ dài vẫn được giữ: `a` trước các từ ba ký tự. `cat` và `dog` cùng tồn tại. Bản `cat` lặp lại được loại đúng với `String.equals`.

Điều kiện thành công ở đây không phải “cứ có `thenComparing` là tốt”. Lý do là tiêu chí cuối cùng phân biệt chính xác các giá trị mà `equals` của `String` phân biệt. Nếu tiêu chí phụ vẫn gom nhiều giá trị khác nhau, vấn đề còn nguyên.

Ví dụ, độ dài rồi ký tự đầu vẫn không đủ để phân biệt `"cat"` và `"car"`. Một tiêu chí phụ có ích cho việc trình bày chưa chắc đủ cho sự duy nhất của tập.

Cũng không lấy mã băm làm một định danh chắc chắn để phân biệt mọi phần tử: hai đối tượng khác nhau vẫn có thể trùng mã băm. `hashCode` không phải mã nhận diện toàn cục không va chạm.

## 7. Hướng sai lệch thứ hai: equals bằng nhau nhưng compare khác 0

Giả sử mô hình `Member` có mã `id` và nhãn hiển thị `label`. Nghiệp vụ chọn nhận diện theo `id`: hai đối tượng cùng mã là cùng thành viên, dù nhãn ở hai lần đọc dữ liệu khác nhau.

Trong chương trình, `Member` là record nhưng có `equals` và `hashCode` được ghi đè tường minh để chỉ dựa vào `id`. Không dùng phép `equals` mặc định theo mọi thành phần của record.

Hai giá trị:

~~~text
7:alpha
7:zulu
~~~

bằng nhau theo `equals`, vì cùng mã 7.

Bây giờ chọn quy tắc “nhãn trước, mã sau”:

~~~java
Comparator<Member> labelThenId =
        Comparator.comparing(Member::label).thenComparingInt(Member::id);
~~~

Nhãn `alpha` và `zulu` khác nhau ngay ở tiêu chí đầu. Bộ so sánh trả kết quả khác 0, nên `TreeSet` nhận cả hai:

~~~text
[7:alpha, 7:zulu]
size = 2
~~~

Nhìn bằng thứ tự, tập có hai vị trí khác nhau. Nhìn bằng hợp đồng `Set` dựa trên `equals`, nó đang giữ hai phần tử bằng nhau.

Tiêu chí mã ở cuối không sửa được điều này. `thenComparingInt` chỉ chạy khi tiêu chí trước cho 0. Khi nhãn đã phân biệt hai đối tượng, việc cùng mã không còn cơ hội làm chúng tương đương.

Đảo thành “mã trước, nhãn sau” cũng chưa chắc sửa được: nếu mã bằng nhau rồi nhãn được dùng để tách tiếp, kết quả cuối vẫn khác 0 cho hai đối tượng bằng nhau theo `equals`. Muốn thứ tự tương thích với phép bằng nhau chỉ theo mã, các giá trị cùng mã phải luôn thuộc cùng một nhóm tương đương.

Trong ví dụ, `Comparator.comparingInt(Member::id)` là quy tắc nhất quán với `equals` của `Member`. Lần thêm `7:zulu` sau `7:alpha` trả `false`. Đại diện đang lưu vẫn là `7:alpha`; khớp quy tắc bằng nhau không có nghĩa tự cập nhật nhãn từ đối tượng đến sau.

## 8. Đừng “sửa” bằng một nhánh trả 0 trước rồi sắp tùy ý

Một ý tưởng thường xuất hiện là:

~~~java
Comparator<Member> shortcut = (left, right) ->
        left.id() == right.id() ? 0 : labelThenId.compare(left, right);
~~~

Đoạn này được dùng trong chương trình để **phát hiện lỗi**, không được đưa vào một `TreeSet`. Nó cố bảo đảm cùng mã thì 0, còn khác mã thì sắp theo nhãn.

Với ba giá trị:

~~~text
a = 7:alpha
b = 7:zulu
c = 8:mike
~~~

ta có:

~~~text
compare(a,b) = 0
a đứng trước c
b đứng sau c
~~~

Nếu `a` và `b` được xem là tương đương về thứ tự, chúng phải có quan hệ cùng dấu với mọi phần tử thứ ba `c`. Ở đây, một phần tử của cùng nhóm lại nằm trước `c`, phần tử còn lại nằm sau `c`. Nhóm tương đương không có vị trí nhất quán trong thứ tự.

Đây là lỗi **hợp đồng của Comparator**, không chỉ là thiếu nhất quán với `equals`. Điều kiện từng cặp `compare == 0` khớp `equals` chưa đủ để chứng minh bộ so sánh hợp lệ.

Một thứ tự hợp lệ còn phải bảo đảm đổi hai đối số thì đổi dấu, tính bắc cầu và sự tương thích với phần tử thứ ba khi so sánh bằng 0. Dùng tiêu chí nhãn có thể thay đổi giữa những đối tượng cùng định danh rồi ép chúng bằng nhau là cách dễ phá điều kiện này.

Đừng dựa vào việc “thêm vài phần tử vẫn chạy” để dùng quy tắc ấy trong cây. Chương trình chỉ tính các kết quả so sánh để chỉ ra mâu thuẫn, tránh tạo một cấu trúc dựa trên bộ so sánh đã biết là không hợp lệ.

## 9. Lựa chọn mô hình trước, rồi lựa chọn cấu trúc

Nếu nhận diện theo mã nhưng muốn hiển thị theo nhãn, hãy tách hai nhu cầu rõ ràng.

Một thiết kế thông dụng là lưu dữ liệu theo mã trong một ánh xạ, rồi tạo danh sách giá trị để sắp xếp theo nhãn khi cần hiển thị. Khi đó:

- Mã quyết định đối tượng nào là cùng thực thể và bản ghi nào được cập nhật.
- Bộ so sánh danh sách quyết định cách trình bày.
- Hai phiên bản nhãn của cùng mã không bị một `TreeSet` nhận thành hai thành viên chỉ vì chúng đứng khác vị trí.

Một lựa chọn khác là dùng các giá trị ảnh chụp bất biến có phép `equals` theo toàn bộ dữ liệu của ảnh chụp. Khi đó, hai ảnh chụp cùng mã nhưng nhãn khác có thể cố ý là hai giá trị khác nhau. Tuy nhiên, đây là thay đổi mô hình bằng nhau; phải phù hợp yêu cầu thực, không chỉ nhằm làm một bộ so sánh đang viết trở nên “đúng”.

Nếu yêu cầu thực sự là gom các từ mà không phân biệt chữ hoa/thường, có thể dùng một khóa chuẩn hóa hoặc một kiểu giá trị thể hiện quy tắc bằng nhau đó, cùng `hashCode` tương ứng. Đừng âm thầm để một tập xem `java/JAVA` là cùng giá trị trong khi các phần còn lại của hệ thống tiếp tục xem chúng là hai chuỗi khác nhau.

Với dữ liệu văn bản, quy tắc chuẩn hóa và so sánh phụ thuộc miền sử dụng. Ví dụ ASCII của bài không tự giải quyết mọi quy tắc ngôn ngữ hoặc chữ Unicode. Hãy xác định rõ ý nghĩa khóa thay vì sửa rải rác bằng các thao tác đổi chữ.

## 10. Chương trình đầy đủ kiểm chứng cả hai hướng

Lưu thành `ComparatorEqualsDemo.java`. Chương trình tự tạo dữ liệu, không cần thư viện ngoài JDK và dùng API có trong Java 17.

Hai hàm `matchesEqualsOnSample` và `sameZeroClassSignsOnSample` là công cụ học tập để kiểm tra một mẫu nhỏ. Chúng không phải bộ chứng minh đầy đủ cho mọi đầu vào của một `Comparator`.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.SortedSet;
import java.util.TreeSet;

public class ComparatorEqualsDemo {
    record Member(int id, String label) {
        @Override
        public boolean equals(Object other) {
            return other instanceof Member member && id == member.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }

        @Override
        public String toString() {
            return id + ":" + label;
        }
    }

    static <T> boolean matchesEqualsOnSample(
            List<T> values, Comparator<? super T> rule) {
        for (T left : values) {
            for (T right : values) {
                if ((rule.compare(left, right) == 0) != Objects.equals(left, right)) {
                    return false;
                }
            }
        }
        return true;
    }

    static <T> boolean sameZeroClassSignsOnSample(
            List<T> values, Comparator<? super T> rule) {
        for (T left : values) {
            for (T right : values) {
                if (rule.compare(left, right) == 0) {
                    for (T third : values) {
                        if (Integer.signum(rule.compare(left, third))
                                != Integer.signum(rule.compare(right, third))) {
                            return false;
                        }
                    }
                }
            }
        }
        return true;
    }

    public static void main(String[] args) {
        Comparator<String> byLength = Comparator.comparingInt(String::length);
        SortedSet<String> coarse = new TreeSet<>(byLength);
        System.out.println("coarse add cat=" + coarse.add("cat"));
        System.out.println("coarse add dog=" + coarse.add("dog"));
        System.out.println("cat equals dog=" + "cat".equals("dog"));
        System.out.println("coarse compare=" + byLength.compare("cat", "dog"));
        System.out.println("coarse=" + coarse);
        System.out.println("coarse contains owl=" + coarse.contains("owl"));
        System.out.println("coarse remove owl=" + coarse.remove("owl"));
        System.out.println("coarse after remove=" + coarse);

        Comparator<String> lengthThenText =
                byLength.thenComparing(Comparator.naturalOrder());
        SortedSet<String> refined = new TreeSet<>(lengthThenText);
        refined.addAll(List.of("dog", "a", "cat", "cat"));
        System.out.println("refined=" + refined);
        System.out.println("refined consistent sample="
                + matchesEqualsOnSample(List.of("a", "cat", "dog"), lengthThenText));
        System.out.println("coarse consistent sample="
                + matchesEqualsOnSample(List.of("a", "cat", "dog"), byLength));

        Member alpha = new Member(7, "alpha");
        Member zulu = new Member(7, "zulu");
        Member mike = new Member(8, "mike");
        List<Member> members = List.of(alpha, zulu, mike);
        Comparator<Member> labelThenId =
                Comparator.comparing(Member::label).thenComparingInt(Member::id);
        SortedSet<Member> tooFine = new TreeSet<>(labelThenId);
        System.out.println("member equals=" + alpha.equals(zulu));
        System.out.println("label comparison sign="
                + Integer.signum(labelThenId.compare(alpha, zulu)));
        System.out.println("too fine first add=" + tooFine.add(alpha));
        System.out.println("too fine second add=" + tooFine.add(zulu));
        System.out.println("too fine=" + tooFine);
        System.out.println("too fine size=" + tooFine.size());
        System.out.println("too fine contains same id="
                + tooFine.contains(new Member(7, "probe")));

        Comparator<Member> byId = Comparator.comparingInt(Member::id);
        SortedSet<Member> identitySet = new TreeSet<>(byId);
        identitySet.add(alpha);
        System.out.println("by id second add=" + identitySet.add(zulu));
        System.out.println("by id=" + identitySet);
        System.out.println("by id contains same id="
                + identitySet.contains(new Member(7, "probe")));
        System.out.println("by id consistent sample="
                + matchesEqualsOnSample(members, byId));

        Comparator<Member> shortcut = (left, right) ->
                left.id() == right.id() ? 0 : labelThenId.compare(left, right);
        System.out.println("shortcut pair consistency="
                + matchesEqualsOnSample(members, shortcut));
        System.out.println("shortcut equal pair=" + shortcut.compare(alpha, zulu));
        System.out.println("shortcut third signs="
                + Integer.signum(shortcut.compare(alpha, mike)) + "/"
                + Integer.signum(shortcut.compare(zulu, mike)));
        System.out.println("shortcut zero class compatible="
                + sameZeroClassSignsOnSample(members, shortcut));

        Set<String> folded = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        folded.add("java");
        Set<String> exact = new HashSet<>(List.of("JAVA"));
        System.out.println("sorted equals hashed=" + folded.equals(exact));
        System.out.println("hashed equals sorted=" + exact.equals(folded));
        System.out.println("set hash codes equal=" + (folded.hashCode() == exact.hashCode()));

        BigDecimal shortForm = new BigDecimal("1.0");
        BigDecimal longForm = new BigDecimal("1.00");
        SortedSet<BigDecimal> numeric = new TreeSet<>();
        numeric.add(shortForm);
        System.out.println("decimal equals=" + shortForm.equals(longForm));
        System.out.println("decimal compare=" + shortForm.compareTo(longForm));
        System.out.println("numeric second add=" + numeric.add(longForm));
        System.out.println("numeric size=" + numeric.size());
        Comparator<BigDecimal> valueThenScale =
                Comparator.<BigDecimal>naturalOrder().thenComparingInt(BigDecimal::scale);
        SortedSet<BigDecimal> representations = new TreeSet<>(valueThenScale);
        representations.addAll(List.of(shortForm, longForm));
        System.out.println("representations=" + representations);
        System.out.println("representation consistent sample="
                + matchesEqualsOnSample(List.of(shortForm, longForm), valueThenScale));

        List<String> display = new ArrayList<>(List.of("cat", "dog", "cat"));
        display.sort(byLength);
        System.out.println("sorted list=" + display);
        System.out.println("sorted list size=" + display.size());
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 ComparatorEqualsDemo.java
java ComparatorEqualsDemo
~~~

Dùng JDK 17 trở lên. `--release 17` yêu cầu trình biên dịch kiểm tra mã và API theo Java 17. Tên lớp `public` phải khớp tên tệp.

Kết quả chuẩn:

~~~text
coarse add cat=true
coarse add dog=false
cat equals dog=false
coarse compare=0
coarse=[cat]
coarse contains owl=true
coarse remove owl=true
coarse after remove=[]
refined=[a, cat, dog]
refined consistent sample=true
coarse consistent sample=false
member equals=true
label comparison sign=-1
too fine first add=true
too fine second add=true
too fine=[7:alpha, 7:zulu]
too fine size=2
too fine contains same id=false
by id second add=false
by id=[7:alpha]
by id contains same id=true
by id consistent sample=true
shortcut pair consistency=true
shortcut equal pair=0
shortcut third signs=-1/1
shortcut zero class compatible=false
sorted equals hashed=true
hashed equals sorted=false
set hash codes equal=false
decimal equals=false
decimal compare=0
numeric second add=false
numeric size=1
representations=[1.0, 1.00]
representation consistent sample=true
sorted list=[cat, dog, cat]
sorted list size=3
~~~

## 11. Đọc kết quả theo từng hợp đồng

### 11.1. Gom quá nhiều giá trị

`coarse add dog=false` xác nhận rằng `dog` không có thành viên riêng sau `cat`. `cat equals dog=false` đi cùng `coarse compare=0` xác nhận đúng hướng sai lệch thứ nhất.

`coarse contains owl=true` và `coarse remove owl=true` cho thấy sai lệch ảnh hưởng cả truy vấn và xóa. Sau lời gọi xóa, tập rỗng dù đối tượng dùng để tìm là chuỗi chưa từng được thêm.

Không thể kết luận `remove` đã tìm cùng tham chiếu hoặc cùng nội dung chuỗi. Nó tìm thấy phần tử tương đương theo bộ so sánh.

### 11.2. Tiêu chí phụ khớp phép bằng nhau

`refined=[a, cat, dog]` giữ được các chuỗi khác nhau và vẫn loại bản `cat` trùng. `refined consistent sample=true` cho biết trên mẫu được đưa vào, mọi cặp đã khớp điều kiện `compare == 0` và `equals`.

Lập luận theo cấu trúc quy tắc còn mạnh hơn kết quả mẫu: với chuỗi khác `null`, so sánh toàn bộ nội dung ở tiêu chí cuối chỉ cho 0 khi nội dung bằng nhau. Vì vậy, ta biết lý do quy tắc đó phù hợp với `String.equals`, chứ không chỉ thấy ba từ được xử lý đúng.

### 11.3. Tách những đối tượng bằng nhau

`member equals=true` nhưng `label comparison sign=-1` cho biết hai thành viên cùng mã bị quy tắc nhãn tách ra. Cả hai lần thêm đều trả `true` và kích thước bằng 2.

`too fine contains same id=false` sử dụng một đối tượng mã 7, nhãn `probe`. Mặc dù nó bằng các thành viên mã 7 theo `equals`, tìm kiếm không gặp vị trí tương đương theo nhãn. Như vậy, không chỉ số lượng bị sai với ý nghĩa định danh; cách kiểm tra sự có mặt cũng bị lệch.

### 11.4. Sửa theo đúng định danh

Với `byId`, lần thêm cùng mã trả `false`, tập giữ `[7:alpha]` và truy vấn bằng mã 7 với nhãn khác trả `true`.

Điều này khớp phép bằng nhau của mô hình. Nếu mục tiêu là thay nhãn hiện có, cần thao tác cập nhật dữ liệu theo hợp đồng khác; không suy từ giá trị `false` của `add` rằng thông tin `zulu` đã được nhập vào đối tượng cũ.

### 11.5. Kiểm tra từng cặp chưa đủ

`shortcut pair consistency=true` xuất hiện trên mẫu ba thành viên, nhưng `shortcut third signs=-1/1` và `shortcut zero class compatible=false` chỉ ra mâu thuẫn với phần tử thứ ba.

Hàm kiểm tra cặp không sai: nó chỉ kiểm tra đúng một thuộc tính được giao. Sai lầm sẽ là diễn giải kết quả của hàm ấy như chứng minh đầy đủ về tính hợp lệ của bộ so sánh.

Đó cũng là cách đọc mọi kiểm thử: kết quả `true` chỉ có ý nghĩa trong phạm vi thuộc tính và dữ liệu đã kiểm tra.

## 12. Sai lệch có thể phá đối xứng của phép bằng nhau giữa hai tập

Chương trình tạo hai tập, mỗi tập một phần tử:

~~~text
folded: TreeSet dùng so sánh không phân biệt hoa/thường, chứa "java"
exact:  HashSet dùng String.equals, chứa "JAVA"
~~~

Không có thao tác đổi nội dung chuỗi. Hai cấu trúc đang dùng hai cách hiểu khác nhau về “có chứa giá trị này”.

Kết quả:

~~~text
sorted equals hashed=true
hashed equals sorted=false
~~~

Theo hợp đồng thông thường của `equals`, nếu `x.equals(y)` đúng thì `y.equals(x)` cũng phải đúng. Hai kết quả ở đây làm lộ sự không tương thích do tập sắp xếp dùng thứ tự không nhất quán với `String.equals`. Không nên diễn giải đây là quyền được chọn chiều gọi `equals` để lấy kết quả có lợi. [Java 17: Object.equals, tính đối xứng](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)).

Lý do trong các lớp của ví dụ có thể theo dõi trực tiếp. Cách triển khai `equals` được kế thừa từ `AbstractSet` kiểm tra cùng kích thước rồi hỏi tập đang nhận lời gọi có chứa mọi thành viên của tập kia không.

- `folded.equals(exact)` dùng phép chứa của `folded`. Chuỗi `JAVA` tương đương với `java` theo bộ so sánh không phân biệt hoa/thường, nên kết quả là `true`.
- `exact.equals(folded)` dùng phép chứa của `HashSet` với `String.equals`. Chuỗi `java` khác `JAVA`, nên kết quả là `false`.

Đây là ví dụ một phần tử để loại bỏ ảnh hưởng của thứ tự duyệt hoặc kích thước. Vấn đề gốc là hai quan hệ bằng nhau không khớp.

Không phải mọi bộ dữ liệu với một comparator không nhất quán đều làm phép bằng nhau lộ sai ngay. Một ví dụ phản chứng là đủ để biết rằng bạn không còn có thể dựa vào hợp đồng chung.

## 13. hashCode vẫn quan trọng dù TreeSet không tìm bằng băm

Có thể nghĩ rằng dùng cây thì không cần quan tâm `hashCode`. Cần tách hai vai trò:

1. Cách `TreeSet` tìm vị trí thành viên chủ yếu dựa vào so sánh.
2. Bản thân tập và phần tử vẫn là đối tượng Java có hợp đồng `equals/hashCode`.

Trong chương trình, `Member.equals` được ghi đè theo mã nên `Member.hashCode` cũng dựa trên mã. Hai thành viên mã 7 bằng nhau phải có cùng mã băm, dù nhãn khác. Đây là yêu cầu của đối tượng, không phụ thuộc bạn đang đặt nó vào `HashSet` hay `TreeSet`.

Mã băm của một tập theo `AbstractSet` được tính từ mã băm các phần tử, không từ ý nghĩa của `Comparator`. Với ví dụ `java/JAVA`, chương trình in:

~~~text
set hash codes equal=false
~~~

Trong khi một chiều `equals` vừa trả `true`, kết quả này còn làm lộ vấn đề với yêu cầu những đối tượng bằng nhau phải có cùng mã băm. Đổi riêng hàm băm của một tập để gom theo bộ so sánh không sửa được toàn bộ sai lệch với `String.equals` ở các nơi khác. [Java 17: AbstractSet.equals và hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSet.html).

Không thể sửa một `Comparator` không nhất quán bằng cách thêm `hashCode` vào quá trình so sánh. Mã băm chỉ cần giống nhau cho các giá trị bằng nhau; nó được phép trùng với các giá trị khác nhau. Nó không cung cấp một thứ tự hoàn chỉnh thay cho mô hình giá trị.

## 14. Thứ tự tự nhiên cũng cần được kiểm tra: BigDecimal

Vấn đề không chỉ nằm ở lambda do bạn tự viết. `TreeSet` không nhận `Comparator` riêng sẽ dùng thứ tự tự nhiên từ `Comparable`, và quan hệ tương đương của `compareTo` cũng có thể khác `equals`.

Với:

~~~text
new BigDecimal("1.0")
new BigDecimal("1.00")
~~~

`compareTo` trả 0 vì cùng giá trị số. `equals` trả `false` vì ngoài giá trị số còn xét cách biểu diễn theo `scale`. Trong mẫu này, thang đo lần lượt là 1 và 2.

Chương trình cho:

~~~text
numeric second add=false
numeric size=1
~~~

Đây là hành vi theo quan hệ thứ tự tự nhiên của kiểu. Tài liệu `BigDecimal` có nêu sự khác nhau đó và lưu ý khi dùng trong các cấu trúc sắp xếp. [Java 17: BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).

Nếu muốn phân biệt các biểu diễn theo đúng `BigDecimal.equals`, ví dụ dùng:

~~~java
Comparator<BigDecimal> valueThenScale =
        Comparator.<BigDecimal>naturalOrder().thenComparingInt(BigDecimal::scale);
~~~

So sánh giá trị số trước; khi cùng giá trị thì so sánh `scale`. Cùng giá trị số và cùng `scale` phù hợp với phép bằng nhau của `BigDecimal`. Hai biểu diễn trên được giữ thành `[1.0, 1.00]`.

Đây không phải phép làm tròn, cũng không đổi giá trị số hay thang đo của đối tượng. Nó chỉ chọn một thứ tự phân biệt thêm điều mà `equals` đang phân biệt.

Nếu nghiệp vụ chỉ cần duy nhất theo giá trị số, hãy chọn mô hình khóa thể hiện đúng ý đó và dùng nhất quán. Không tự suy rằng khác biệt biểu diễn luôn quan trọng hoặc luôn phải bị loại; đó là quyết định dữ liệu, còn bài học chỉ chỉ ra hai quan hệ hiện có.

## 15. Một Comparator không nhất quán vẫn có thể dùng để sắp danh sách

Không nhất quán với `equals` không tự động có nghĩa phép so sánh vi phạm mọi hợp đồng. Bộ so sánh theo độ dài của chuỗi vẫn cho một thứ tự nhóm rõ ràng và có thể dùng để sắp một danh sách các từ.

Phần cuối chương trình cho:

~~~text
sorted list=[cat, dog, cat]
sorted list size=3
~~~

`List.sort` sắp các phần tử; nó không thực hiện việc loại trùng kiểu `TreeSet`. Vì vậy, dùng tiêu chí độ dài không làm `dog` hoặc bản `cat` lặp biến mất. [Java 17: List.sort](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).

Phân biệt hai yêu cầu:

| Nhu cầu | Cấu trúc và quy tắc cần cân nhắc |
| --- | --- |
| Giữ mọi bản ghi, chỉ thay trình tự hiển thị | Danh sách và một Comparator hợp lệ cho cách trình bày |
| Giữ một phần tử cho mỗi giá trị theo equals, luôn có thứ tự | Tập sắp xếp với thứ tự nhất quán với equals |
| Nhận diện và cập nhật theo mã, trình bày theo trường khác | Cấu trúc lưu theo mã, rồi danh sách/khung nhìn phục vụ trình bày |
| Cố ý gom theo một khóa riêng | Mô hình khóa hoặc nhóm rõ ràng, không đánh đồng ngầm với equals của dữ liệu gốc |

`Comparator` dùng cho danh sách vẫn phải tuân thủ hợp đồng so sánh. Ví dụ `shortcut` sai với phần tử thứ ba không trở thành hợp lệ chỉ vì chuyển từ cây sang danh sách.

Điều được phép khác ở đây là quan hệ bằng 0 so với `equals` khi thao tác chỉ cần một thứ tự sắp xếp thích hợp. Không phải mọi lần hai đối tượng cùng hạng đều phải khiến chúng trở thành cùng thực thể của miền nghiệp vụ.

## 16. Cách kiểm tra có ý nghĩa

Đối với một quy tắc mới, nên chuẩn bị các cặp theo đặc tính của mô hình:

- Cùng tham chiếu.
- Khác tham chiếu nhưng bằng nhau theo `equals`.
- Cùng khóa sắp xếp chính nhưng khác một thuộc tính mà `equals` xét.
- Khác khóa sắp xếp chính.
- Những giá trị biên của các trường số hoặc chuỗi.
- Các giá trị `null` chỉ khi hợp đồng thực sự cho phép chúng.

Hàm `matchesEqualsOnSample` so sánh mọi cặp trong mẫu và kiểm tra hai mệnh đề `compare == 0` và `Objects.equals` có cùng giá trị `boolean` không. Nó không cần biết bộ so sánh trả -1, -20 hay 20; chỉ cần phân biệt 0 với khác 0 cho thuộc tính này.

Ngoài ra, kiểm tra các thuộc tính của phép so sánh:

~~~text
đổi hai đối số → đảo dấu
a trước b, b trước c → a trước c
a tương đương b → chúng phải có cùng hướng so với mọi c
~~~

Hàm `sameZeroClassSignsOnSample` chỉ kiểm tra thuộc tính cuối trên mẫu, không kiểm tra đầy đủ tất cả các thuộc tính còn lại. Tên hàm cố ý giới hạn điều nó khẳng định.

Chi phí của kiểm tra cặp tăng theo bình phương số phần tử; kiểm tra bộ ba tăng theo lập phương. Các hàm trong bài phù hợp với mẫu nhỏ được chọn để giải thích và tìm phản ví dụ, không phải thao tác cần chạy lại sau mỗi lần thêm vào tập thật.

Một mẫu kiểm thử đi qua không chứng minh đúng cho miền vô hạn. Kết hợp bằng chứng chạy với lập luận về những thuộc tính được `equals` và `Comparator` dùng. Mẫu có hai phiên bản nhãn của cùng mã thường có ích hơn rất nhiều bản ghi mà mọi mã và mọi nhãn đều khác nhau.

## 17. Dữ liệu và quy tắc phải ổn định trong thời gian lưu

Tính nhất quán không chỉ là ảnh chụp tại một thời điểm. Nếu bạn thay đổi trường dùng trong phép so sánh khi đối tượng còn nằm trong `TreeSet`, cây không tự biết phải tổ chức lại vị trí.

Nếu `equals` dựa vào một nhóm trường và `Comparator` dựa vào nhóm trường khác, cập nhật dữ liệu có thể vừa làm sai cách tìm trong cây, vừa thay đổi quan hệ giữa hai đối tượng.

Cách dễ kiểm soát là dùng giá trị bất biến cho các thuộc tính liên quan đến thứ tự và nhận diện. Ví dụ `Member` dùng các thành phần record không có thao tác gán lại; hai nhãn khác nhau được biểu diễn bằng hai đối tượng khác nhau để ta quan sát quy tắc rõ ràng.

Không giữ một bộ so sánh phụ thuộc vào một cấu hình thay đổi ngầm, chẳng hạn một cờ đảo chiều được đổi sau khi đã tạo tập. Một thứ tự đúng ở thời điểm thêm nhưng đổi nghĩa khi tìm không phải nền tảng ổn định cho cấu trúc sắp xếp.

Cũng không dùng các lối phân biệt giả như trả 1 với hai phần tử tương đương, lấy số ngẫu nhiên hoặc lấy địa chỉ tưởng tượng để buộc tập giữ mọi thứ. Chúng không thay thế mô hình giá trị và có thể phá điều kiện dấu hoặc bắc cầu.

## 18. Những nhầm lẫn cần sửa trong cách đọc mã

| Nhầm lẫn | Điều cần kiểm tra |
| --- | --- |
| “Hai đối tượng khác nhau nên compare phải khác 0” | “Khác tham chiếu” không đồng nghĩa “khác theo equals” |
| “Chỉ cần compare bằng 0 thì equals đúng” | Cần cả chiều equals đúng thì compare bằng 0 |
| “TreeSet sẽ dùng equals nếu comparator phân biệt chưa đủ” | Tập dùng kết quả so sánh để nhận diện tương đương |
| “Thêm thenComparing(id) luôn sửa được” | Kiểm tra trường hợp cùng id nhưng khác tiêu chí đứng trước |
| “Trả 0 sớm khi equals đúng là đủ” | Phải kiểm tra quan hệ với phần tử thứ ba và tính bắc cầu |
| “HashCode là tiêu chí phụ duy nhất đáng tin cậy” | Mã băm được phép va chạm |
| “Có cùng hashCode nghĩa là equals đúng” | Hợp đồng chỉ yêu cầu chiều bằng nhau thì cùng mã băm |
| “Record mặc định nhận diện theo id” | Record mặc định xét các thành phần; bài có ghi đè tường minh cho Member |
| “Một chiều set.equals đúng là đủ” | equals phải đối xứng và tương thích với hashCode |
| “Thứ tự tự nhiên có sẵn chắc chắn khớp equals” | BigDecimal là một trường hợp cần biết |
| “Không nhất quán với equals thì không thể dùng comparator để sort” | Một Comparator hợp lệ vẫn có thể dùng cho danh sách; tách yêu cầu sắp xếp và duy nhất |
| “Mẫu kiểm tra đúng là chứng minh mọi dữ liệu đúng” | Xét miền dữ liệu, thuộc tính mô hình và các phản ví dụ có chủ đích |
| “equals ở đây là Comparator.equals” | Đang kiểm tra equals của phần tử, không phải của đối tượng bộ so sánh |

Các lỗi thường khó thấy nhất khi mỗi khóa sắp xếp trong mẫu đều khác nhau. Hãy chủ động tạo dữ liệu trùng khóa chính và các phiên bản khác thông tin nhưng cùng định danh trước khi kết luận.

## 19. Thực hành có lời giải

### Bài 1: kiểm tra hai chiều

Một cặp đối tượng có `a.equals(b) == false` và `compare(a,b) == 0`. Cặp đó có nhất quán không? Nếu đảo lại thành `equals == true` và `compare != 0` thì sao?

**Lời giải:** Cả hai đều không nhất quán. Trường hợp đầu bộ so sánh gom quá nhiều giá trị; trường hợp sau tách những giá trị mà equals xem là một. Phải kiểm tra điều kiện hai chiều.

### Bài 2: dự đoán tìm và xóa

Tập chuỗi dùng bộ so sánh chỉ theo độ dài, hiện chứa `"red"`. `contains("sky")` và `remove("sky")` trả gì?

**Lời giải:** Cả hai trả `true` trong ví dụ này vì cùng độ dài ba. Lần xóa loại đại diện `red` khỏi tập. Nó không yêu cầu chuỗi sky từng được thêm.

### Bài 3: một tiêu chí phụ chưa đủ

Bạn so sánh chuỗi theo độ dài, rồi theo ký tự đầu. `"cat"` và `"car"` có còn bị gom không?

**Lời giải:** Có. Chúng cùng độ dài và cùng ký tự đầu, nên cả hai tiêu chí đều cho 0. Với phép bằng nhau của String, cần tiêu chí cuối đủ để phân biệt toàn bộ nội dung, chẳng hạn thứ tự tự nhiên của chuỗi.

### Bài 4: mã trước, nhãn sau

Member có equals chỉ theo id. Comparator so sánh id trước, nếu bằng thì so sánh label. Hai giá trị `5:old` và `5:new` có nhất quán không?

**Lời giải:** Không. Equals xem cùng mã 5 là bằng nhau, nhưng tiêu chí label tách chúng thành kết quả so sánh khác 0. Đưa id lên đầu không tự bỏ ảnh hưởng của tiêu chí phụ.

### Bài 5: vì sao nhánh trả 0 chưa đủ?

Cho `a=7:alpha`, `b=7:zulu` và `c=8:mike`. Quy tắc trả 0 khi cùng mã, còn khác mã thì so sánh nhãn. Điều kiện nào bị phá?

**Lời giải:** a và b so sánh bằng 0 nhưng a đứng trước c, b đứng sau c. Những đối tượng tương đương về thứ tự phải có cùng dấu khi so với phần tử thứ ba. Quy tắc này vi phạm hợp đồng Comparator, dù phép kiểm tra compare bằng 0 khớp equals trên mẫu.

### Bài 6: lựa chọn mô hình

Bạn cần một người duy nhất theo mã, thường cập nhật tên hiển thị và đôi khi xuất danh sách theo tên. Có nên dùng TreeSet sắp theo tên rồi mã để vừa lưu vừa cập nhật không?

**Lời giải:** Cần thận trọng: hai phiên bản tên của cùng mã có thể trở thành hai phần tử nếu equals theo mã. Một cấu trúc lưu/cập nhật theo mã và danh sách được sắp theo tên khi trình bày thường tách đúng hai nhu cầu. Chọn mô hình trước khi chọn bộ so sánh.

### Bài 7: hai tập và đối xứng

Một TreeSet không phân biệt hoa/thường chứa `"abc"`; một HashSet chứa `"ABC"`. Có nên dùng kết quả một chiều equals để khẳng định hai tập trao đổi được trong mọi mã xử lý Set không?

**Lời giải:** Không. Hai tập đang dùng hai quan hệ nhận diện khác nhau. Như chương trình đã chỉ ra với java/JAVA, phép bằng nhau có thể khác khi đổi chiều và gây vấn đề hợp đồng hashCode. Cần thống nhất mô hình khóa, không chọn chiều gọi thuận lợi.

### Bài 8: sort danh sách

Một danh sách chứa `cat, dog, cat` được sắp theo độ dài. Comparator không nhất quán với String.equals có làm danh sách tự bỏ dog không?

**Lời giải:** Không. Sắp xếp danh sách không phải loại trùng theo cơ chế của TreeSet. Ba phần tử vẫn tồn tại. Comparator vẫn phải hợp lệ về thứ tự; điều khác là danh sách không dùng compare bằng 0 để quyết định bỏ thành viên.

### Bài 9: BigDecimal

Bạn muốn giữ phân biệt `3.0` và `3.00` theo BigDecimal.equals. Chỉ dùng thứ tự tự nhiên trong TreeSet có đáp ứng không? Một tiêu chí nào có thể bổ sung sau so sánh giá trị?

**Lời giải:** Thứ tự tự nhiên cho compareTo bằng 0 nên không giữ hai thành viên riêng. Ví dụ trong bài bổ sung scale sau so sánh giá trị số để phân biệt các biểu diễn theo phép bằng nhau của BigDecimal. Việc đó không làm tròn hoặc thay dữ liệu.

### Bài 10: đọc phạm vi của một kiểm tra

`matchesEqualsOnSample` trả true trên mười đối tượng. Có thể kết luận comparator hợp lệ và nhất quán trên mọi dữ liệu của lớp không?

**Lời giải:** Không. Hàm chỉ kiểm tra quan hệ compare bằng 0 với equals trên các cặp thuộc mẫu, chưa kiểm tra đầy đủ hợp đồng thứ tự và chưa bao phủ toàn miền. Ví dụ shortcut là bằng chứng trực tiếp rằng một thuộc tính đi qua không thay thế thuộc tính khác.

## 20. Quy trình ngắn khi xem lại một Comparator dùng cho tập

Trước hết, viết bằng lời định nghĩa `equals` của phần tử. Sau đó, viết điều kiện chính xác để `Comparator` trả 0. Hai điều kiện ấy phải trùng nhau trên miền dữ liệu được phép nếu muốn tuân theo hợp đồng chung của `Set`.

Tiếp theo, kiểm tra tính hợp lệ của thứ tự với bộ ba phần tử, đặc biệt khi có nhánh xử lý riêng cho “cùng mã”. Xem những trường dùng để so sánh có thay đổi trong thời gian lưu không.

Cuối cùng, thử cả `add`, `contains` và `remove` bằng một đối tượng khác tham chiếu nhưng cùng giá trị nghiệp vụ. Khi hệ thống trao đổi dữ liệu giữa các cách triển khai Set, kiểm tra cả hai chiều equals và sự phù hợp của hashCode.

Nếu quy tắc bạn cần chỉ phục vụ hiển thị, hãy đặt nó ở lớp xử lý trình tự phù hợp. Không buộc một tập sắp xếp đồng thời giải quyết hai định nghĩa khác nhau về “cùng một phần tử”.
