# Chính sách null và việc không bảo đảm thứ tự duyệt

## 1. Hai câu hỏi độc lập khi dùng một Set dựa trên băm

Khi dùng HashSet, cần phân biệt:

1. **Những giá trị nào được phép có mặt?** HashSet cho phép null, nhưng vẫn chỉ có tối đa một lần hiện diện của null.
2. **Các giá trị được duyệt theo thứ tự nào?** HashSet không bảo đảm thứ tự thêm, thứ tự sắp xếp hay một thứ tự duyệt cố định theo thời gian.

Một chính sách cho phép null không tạo ra vị trí ưu tiên cho null. Việc null xuất hiện đầu trong một lần in không phải hợp đồng rằng nó luôn đứng đầu.

Tương tự, “dùng băm” là một cơ chế lưu trữ và tìm kiếm, không tự quyết định mọi chính sách của lớp. LinkedHashSet cũng dựa trên băm nhưng bổ sung bảo đảm thứ tự thêm. Một tập khóa của ConcurrentHashMap cũng dựa trên băm nhưng không cho thêm null.

Vì vậy, câu đúng cần gắn với **lớp hoặc cách tạo cụ thể**, không chỉ với nhãn Set dùng băm.

Tài liệu [HashSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html) nêu cả việc cho phép null và việc không bảo đảm thứ tự duyệt. Bài này lấy HashSet làm trường hợp chính, dùng Java 17 trở lên và thao tác tuần tự trong một luồng.

## 2. null trong HashSet là một giá trị hiện diện, không phải tập rỗng

### 2.1. Có tối đa một null

Với một HashSet có thể sửa thông thường:

| Lời gọi | Ý nghĩa |
| --- | --- |
| add(null) khi chưa có null | Thêm null, trả true |
| add(null) khi đã có null | Không thêm bản thứ hai, trả false |
| contains(null) | Hỏi trong tập có null không |
| remove(null) khi đang có | Xóa null, trả true |
| remove(null) khi không có | Không đổi tập, trả false |

Set không giữ số lần xuất hiện. Nếu nguồn có mười giá trị null, chuyển chúng vào HashSet không giữ lại thông tin “đã có mười lần thiếu dữ liệu”.

null vẫn được tính vào size. Một tập chỉ có null có size bằng 1 và isEmpty trả false.

### 2.2. null khác chuỗi rỗng và chuỗi "null"

Ba trường hợp này khác nhau:

```text
null       : không có tham chiếu đến một đối tượng String.
""         : một String có nội dung rỗng.
"null"     : một String chứa bốn ký tự n, u, l, l.
```
Một HashSet<String> có thể đồng thời chứa cả ba, vì chúng không phải cùng một giá trị theo quan hệ bằng nhau.

Kiểu tham số String không có nghĩa mọi phần tử chắc chắn khác null. Hệ thống kiểu Java thông thường không tự cấm null chỉ vì biến được khai báo Set<String>.

Đừng tự thay null bằng chuỗi `"null"` hoặc chuỗi rỗng nếu chưa có chính sách nghiệp vụ. Việc thay như vậy có thể gộp dữ liệu thiếu với một giá trị văn bản thật.

### 2.3. HashSet xử lý null không có nghĩa mã gọi được bỏ qua null

HashSet hỗ trợ lưu và hỏi null. Nhưng sau khi lấy phần tử, gọi một phương thức trên tham chiếu null vẫn có thể gây NullPointerException.

```java
// Đoạn minh họa: values có thể chứa null.
for (String value : values) {
    if (value == null) {
        handleMissingValue();
    } else {
        handleText(value);
    }
}
```
Việc HashSet không ném lỗi ở add(null) không bảo đảm một hàm xử lý chuỗi, một comparator hoặc một API nhận collection ở phía sau cũng chấp nhận null.

Nếu ứng dụng không cho dữ liệu thiếu, nên kiểm tra ở ranh giới đầu vào thay vì dựa vào việc HashSet tình cờ cho lưu nó.

## 3. Ví dụ chạy được: thêm, đếm và xóa null

Lưu chương trình vào `HashSetNullSemanticsDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class HashSetNullSemanticsDemo {
    public static void main(String[] args) {
        Set<String> values = new HashSet<>();

        System.out.println("add first null = " + values.add(null));
        System.out.println("add second null = " + values.add(null));
        System.out.println("size after null adds = " + values.size());
        System.out.println("contains null = " + values.contains(null));
        System.out.println("empty while containing null = " + values.isEmpty());

        values.add("");
        values.add("null");
        values.add("A");
        System.out.println("size with distinct text values = " + values.size());
        System.out.println("contains empty text = " + values.contains(""));
        System.out.println("contains literal null text = " + values.contains("null"));

        int nullCount = 0;
        int textCount = 0;
        for (String value : values) {
            if (value == null) {
                nullCount++;
            } else {
                textCount++;
            }
        }
        System.out.println("null elements seen = " + nullCount);
        System.out.println("non-null elements seen = " + textCount);

        System.out.println("remove null = " + values.remove(null));
        System.out.println("remove null again = " + values.remove(null));
        System.out.println("contains null after removal = " + values.contains(null));
        System.out.println("remaining size = " + values.size());
    }
}
```
Biên dịch và chạy:

```shell
javac --release 17 HashSetNullSemanticsDemo.java
java HashSetNullSemanticsDemo
```
Kết quả:

```text
add first null = true
add second null = false
size after null adds = 1
contains null = true
empty while containing null = false
size with distinct text values = 4
contains empty text = true
contains literal null text = true
null elements seen = 1
non-null elements seen = 3
remove null = true
remove null again = false
contains null after removal = false
remaining size = 3
```
Giải thích:

- Hai lần add(null) chỉ tạo một lần hiện diện.
- Tập chứa null không rỗng.
- Thêm chuỗi rỗng, chuỗi "null" và A làm tổng số giá trị phân biệt thành bốn.
- Một lượt duyệt thấy một null và ba String không null.
- Xóa null lần đầu làm tập đổi; lần sau không còn null để xóa.

Chương trình không in cả HashSet theo một thứ tự cố định. Bộ đếm duyệt cho cùng kết quả dù các phần tử được gặp theo thứ tự nào.

Đây cũng là cách kiểm chứng phù hợp với hợp đồng: kiểm tra hiện diện, size và số phần tử thỏa điều kiện, thay vì gán ý nghĩa cho vị trí quan sát được của null.

## 4. Chính sách của collection và ý nghĩa nghiệp vụ không phải một thứ

### 4.1. Cho phép không có nghĩa bắt buộc phải dùng

HashSet cho phép null, nhưng một lớp nghiệp vụ có thể yêu cầu mọi mã đều khác null. Khi đó, có thể kiểm tra trước khi đưa vào tập.

```java
// Đoạn minh họa: Objects thuộc java.util.
String validCode = Objects.requireNonNull(code, "code");
codes.add(validCode);
```
Đây là một chính sách dữ liệu rõ ràng, không cần đổi sang một loại tập khác chỉ để tạo lỗi null.

Ngược lại, nếu null có ý nghĩa được chấp nhận, phải mô tả ý nghĩa đó: thiếu giá trị, chưa xác định hay một trạng thái đặc biệt nào. Set chỉ giữ hiện diện, không tự phân biệt nhiều nguyên nhân khác nhau cùng được mã hóa bằng null.

### 4.2. null của biến Set khác với null là một phần tử

```text
Set<String> values = null;
-> Không có đối tượng Set để gọi phương thức.

Một HashSet đã tạo, có chứa null:
-> Có đối tượng Set; null là một thành viên của nó.
```
Gọi values.contains(null) khi chính values là null vẫn gây NullPointerException trước khi có một thao tác collection hợp lệ.

Một hàm có thể yêu cầu đối số Set không null nhưng cho phép phần tử null. Hoặc nó có thể yêu cầu cả hai đều khác null. Hợp đồng cần nói rõ hai tầng này.

### 4.3. Không dùng null để giữ nhiều bản ghi thiếu riêng biệt

Nếu mỗi bản ghi thiếu cần được theo dõi riêng, đưa tất cả vào cùng một giá trị null trong Set sẽ gộp chúng thành một lần hiện diện.

Có thể cần một kiểu bản ghi có định danh riêng hoặc một collection giữ các lần xuất hiện. Quyết định này thuộc mô hình dữ liệu; một HashSet cho phép null không giải quyết được yêu cầu đếm hay phân biệt từng trường hợp thiếu.

## 5. “Không bảo đảm thứ tự” có nghĩa gì?

### 5.1. Không phải thứ tự thêm

Với đầu vào z, a, m, HashSet không hứa iterator sẽ trả z rồi a rồi m.

Nếu cần giữ thứ tự xuất hiện đầu tiên trong khi loại trùng, phải giữ thông tin đó từ nguồn và chọn một cách biểu diễn có hợp đồng tương ứng, chẳng hạn LinkedHashSet.

### 5.2. Không phải thứ tự sắp xếp

HashSet không tự sắp theo chữ cái, số, id, độ ưu tiên hoặc hashCode.

Ngay cả khi một tập số nhỏ tình cờ in tăng dần, không được lấy quan sát đó làm quy tắc của API. Một bộ dữ liệu khác, cách tạo khác hoặc môi trường khác có thể không tạo ra cùng kết quả.

Muốn phần tử nhỏ nhất, phải dùng một phép chọn theo thứ tự đã định nghĩa, không lấy phần tử đầu iterator rồi đặt tên là minimum.

### 5.3. Không có nghĩa “luôn bị xáo ngẫu nhiên”

Không bảo đảm không đồng nghĩa mỗi lần duyệt đều phải khác lần trước. Trong một môi trường cụ thể, với một trạng thái không đổi, ta có thể quan sát nhiều lần in giống nhau.

Điều đó chưa tạo ra một cam kết cho chương trình được phép dựa vào. Cũng không chứng minh HashSet là một bộ sinh lựa chọn ngẫu nhiên công bằng.

Nếu mục tiêu là chọn ngẫu nhiên, cần thuật toán chọn phù hợp. Nếu mục tiêu là đầu ra xác định, cần thứ tự được quy định rõ. HashSet không tự cung cấp hai điều đó qua “phần tử đầu”.

### 5.4. Không có vị trí đặc biệt được bảo đảm cho null

Một triển khai có thể dùng các quy ước nội bộ để lưu null, nhưng API HashSet không quy định “null luôn được duyệt đầu tiên” hay “null luôn nằm cuối”.

Không kiểm thử hoặc viết thuật toán bằng giả định đó. Chính sách hiện diện và vị trí duyệt là hai hợp đồng khác nhau.

## 6. Vì sao cấu trúc băm không tự giữ thứ tự đầu vào?

Một tập băm tổ chức các giá trị để phục vụ tìm kiếm hiện diện, sử dụng thông tin băm và cấu trúc lưu trữ bên trong.

Thứ tự duyệt quan sát được có thể chịu ảnh hưởng của:

- Hash code và cách các phần tử được phân bố trong bảng.
- Sức chứa và các lần thay đổi cấu trúc.
- Các lần thêm, xóa và trạng thái hiện tại.
- Chi tiết triển khai của phiên bản thư viện/JVM.

Đây là lời giải thích cơ chế, không phải một công thức API để dự đoán thứ tự.

Không cần thuộc cách ánh xạ từng bucket để dùng HashSet đúng. Điều cần nắm là **thông tin về thứ tự thêm không nằm trong bảo đảm của lớp**, nên không thể dùng nó như một danh sách đã lưu lịch sử nhập.

Thêm hoặc xóa có thể làm thứ tự thay đổi, nhưng không bắt buộc mọi thao tác đều phải tạo thứ tự khác. Một bài kiểm tra cố tình thêm phần tử rồi bắt buộc thứ tự đảo đi cũng đang kiểm tra một điều API không yêu cầu.

LinkedHashSet bổ sung liên kết để giữ thứ tự thêm. Nó cho thấy “dùng băm” và “có thứ tự duyệt được bảo đảm” có thể cùng tồn tại nếu lớp có hợp đồng bổ sung.

## 7. Khi đầu ra cần ổn định, phải chọn thứ tự có ý nghĩa

### 7.1. Cần giữ thứ tự xuất hiện đầu tiên

Dùng một nguồn có thứ tự phù hợp rồi đưa trực tiếp vào LinkedHashSet:

```java
// Đoạn minh họa: input có thứ tự gặp được mà chương trình cần giữ.
Set<String> values = new LinkedHashSet<>(input);
```
[LinkedHashSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html) cho phép null và giữ thứ tự thêm. Vì vậy, null có vị trí theo lúc nó được thêm lần đầu như các giá trị khác.

Thêm lại một phần tử đang có không tự đẩy nó xuống cuối. Nếu xóa rồi thêm lại, đó là lần thêm mới và cần được hiểu riêng.

Nếu đã bỏ nguồn và chỉ còn một HashSet, sao chép nó sang LinkedHashSet chỉ giữ thứ tự gặp được từ HashSet lúc sao chép. Nó không khôi phục được lịch sử nhập ban đầu đã không còn được cung cấp.

### 7.2. Cần thứ tự so sánh

Có thể tạo một danh sách từ tập rồi sắp theo quy tắc rõ ràng. Khi có null, comparator cũng phải xử lý null.

```java
// Đoạn minh họa.
List<String> display = new ArrayList<>(values);
display.sort(Comparator.nullsLast(Comparator.naturalOrder()));
```
Trong ví dụ String này:

- Các String không null được so theo thứ tự tự nhiên.
- null được đặt sau các String.
- Việc sắp tạo ra một thứ tự trình bày có chủ đích.
- HashSet nguồn không vì thế mà đổi thành một tập có thứ tự được bảo đảm.

Có thể chọn nullsFirst nếu yêu cầu là đặt null trước. Xem [Comparator của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html) để dùng quy tắc so sánh null phù hợp.

Với kiểu phần tử phức tạp, nếu comparator coi nhiều phần tử khác nhau là ngang nhau, một phép sắp ổn định có thể vẫn giữ thứ tự nguồn không được bảo đảm giữa các phần tử đó. Nếu cần đầu ra hoàn toàn xác định, phải có quy tắc phân biệt phù hợp cho những trường hợp bằng nhau về tiêu chí chính.

### 7.3. Cần duy trì tập đã sắp trong lúc cập nhật

Một cấu trúc có thứ tự như TreeSet có thể đáp ứng yêu cầu đó, nhưng phải kiểm tra comparator, tiêu chí hiện diện và chính sách null.

Không dùng TreeSet theo thứ tự tự nhiên để sao chép mù quáng một HashSet có null rồi mong mọi dữ liệu được chấp nhận. Một nhu cầu mới về thứ tự có thể kéo theo chính sách đầu vào khác.

Bài tập trung vào hợp đồng của HashSet; lựa chọn thứ tự đầu ra cần được quyết định theo yêu cầu cụ thể.

## 8. Ví dụ chạy được: không cần giả định thứ tự HashSet

Lưu vào `HashSetOrderContractDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class HashSetOrderContractDemo {
    public static void main(String[] args) {
        List<String> input = Arrays.asList("z", null, "a", "z", "m");
        Set<String> hash = new HashSet<>(input);

        System.out.println("distinct count = " + hash.size());
        System.out.println("contains every input value = " + hash.containsAll(input));

        Set<String> sameMembers = new HashSet<>(
                Arrays.asList("m", "a", null, "z"));
        System.out.println("same members from another input order = "
                + hash.equals(sameMembers));

        LinkedHashSet<String> insertionOrder = new LinkedHashSet<>(input);
        System.out.println("LinkedHashSet insertion order = " + insertionOrder);

        List<String> sortedForDisplay = new ArrayList<>(hash);
        sortedForDisplay.sort(Comparator.nullsLast(Comparator.naturalOrder()));
        System.out.println("explicit sorted display = " + sortedForDisplay);

        String arbitrary = hash.iterator().next();
        System.out.println("iterator first belongs to set = "
                + hash.contains(arbitrary));
    }
}
```
Biên dịch và chạy:

```shell
javac --release 17 HashSetOrderContractDemo.java
java HashSetOrderContractDemo
```
Kết quả:

```text
distinct count = 4
contains every input value = true
same members from another input order = true
LinkedHashSet insertion order = [z, null, a, m]
explicit sorted display = [a, m, z, null]
iterator first belongs to set = true
```
Những điều chương trình làm có chủ đích:

1. Dùng Arrays.asList để tạo đầu vào có null; không dùng List.of vì factory đó từ chối null.
2. HashSet có bốn giá trị phân biệt từ năm lần xuất hiện đầu vào.
3. Hai HashSet tạo từ thứ tự khác nhau vẫn bằng nhau về thành viên.
4. LinkedHashSet giữ z, null, a, m theo thứ tự gặp lần đầu.
5. Danh sách được sắp rõ ràng có kết quả a, m, z, null.
6. Phần tử đầu iterator được gọi là arbitrary, tức một lựa chọn theo thứ tự duyệt của triển khai, không được gọi là phần tử nhập đầu hay phần tử nhỏ nhất.

Dòng cuối chỉ kiểm tra rằng phần tử được iterator trả về thật sự thuộc tập. Chương trình không in một giá trị cố định cho arbitrary.

Ngay cả nếu một lần chạy cụ thể trả null trước, output hợp đồng vẫn không được viết thành “iterator luôn trả null”. Tập này không rỗng, nên next có một phần tử để trả; nếu tập rỗng, Iterator.next có hợp đồng lỗi khác, không dùng null như dấu hiệu kết thúc chung.

## 9. Không phải mọi Set dùng băm đều nhận null

### 9.1. Phải xem lớp hoặc cách tạo cụ thể

| Cách tạo | Chính sách null cần hiểu | Thứ tự cần hiểu |
| --- | --- | --- |
| new HashSet<>() | Cho phép tối đa một null | Không bảo đảm thứ tự duyệt |
| new LinkedHashSet<>() | Cho phép tối đa một null | Thứ tự thêm |
| ConcurrentHashMap.newKeySet() | Không cho thêm null | Không dùng như tập giữ thứ tự thêm hoặc đã sắp |
| Set.of(...) / Set.copyOf(...) | Từ chối phần tử null | Không dựa vào thứ tự duyệt được bảo đảm |
| Collections.unmodifiableSet(source) | Đọc qua source; không tự lọc hay cấm null đã có | Đọc thứ tự qua source, không tự tạo thứ tự mới |

Hai dòng factory Set là ví dụ về hợp đồng collection; không cần và không nên dựa vào một giả định rằng chúng luôn có cùng triển khai nội bộ với HashSet.

[ConcurrentHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html) không cho null làm khóa; tập tạo bởi newKeySet được hậu thuẫn bằng cấu trúc đó. Điều này cho thấy null là chính sách của lớp, không phải hệ quả bắt buộc của việc có hay không có bảng băm.

Không suy tiếp rằng “mọi collection đồng thời đều có cùng chính sách null”. Cần xem hợp đồng của lựa chọn thực tế.

### 9.2. Thay lớp có thể làm lộ dữ liệu null đang tồn tại

Một đoạn mã đang dùng HashSet có thể chấp nhận null từ lâu. Khi chuyển sang một cách tạo khác để có đầu ra không sửa được hoặc để dùng cấu trúc khác, null có thể bị từ chối.

Vì vậy, thay lớp collection không chỉ là thay tốc độ. Cần kiểm tra xem chính sách dữ liệu và bảo đảm thứ tự có còn phù hợp.

Nếu quyết định bỏ null, hãy làm rõ đó là lọc dữ liệu theo chính sách, không coi nó là một phép sao chép giữ nguyên nội dung. Nếu quyết định báo lỗi, cần để người gọi hiểu điều kiện đầu vào.

## 10. Bản sao, vùng nhìn không sửa được và null

### 10.1. HashSet copy giữ null nhưng không tạo bảo đảm thứ tự

new HashSet<>(source) có thể tạo cấu trúc Set độc lập với cùng các giá trị hợp lệ, kể cả null nếu nguồn có null.

Việc thêm một thành viên mới vào source sau khi sao chép không tự thêm nó vào bản sao. Nhưng bản sao đó vẫn không bảo đảm thứ tự duyệt, và không tự sao chép sâu từng đối tượng phần tử.

### 10.2. Set.copyOf không nhận null

[Set.copyOf trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)) trả một Set không sửa cấu trúc được và từ chối nguồn chứa null.

Do đó, ý định “chỉ muốn bảo vệ khỏi add/remove” không có nghĩa thay mọi phép copy bằng Set.copyOf sẽ luôn giữ cùng hợp đồng dữ liệu.

Nếu null là dữ liệu hợp lệ, cần một cách xuất kết quả phù hợp với null. Nếu null không hợp lệ, có thể dùng bước kiểm tra đó như một phần chính sách rõ ràng, nhưng đừng giấu việc dữ liệu bị từ chối.

### 10.3. unmodifiableSet là vùng nhìn đọc qua nguồn

Theo [Collections.unmodifiableSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set)), vùng nhìn không cho sửa qua chính nó nhưng các truy vấn đọc qua tập nguồn.

Nếu source là HashSet có null, vùng nhìn có thể đọc thấy null. Nếu một biến khác tiếp tục thêm/xóa source, vùng nhìn phản ánh thay đổi đó.

Đây không phải ảnh chụp độc lập.

Nếu cần vừa tách cấu trúc khỏi nguồn, vừa không cho sửa qua kết quả và vẫn chấp nhận null, có thể tạo bản sao riêng rồi bọc nó:

```java
// Đoạn minh họa: bản sao không được đưa ra ngoài qua tham chiếu khác.
Set<String> result = Collections.unmodifiableSet(new HashSet<>(source));
```
Mẫu này vẫn không tạo thứ tự duyệt được bảo đảm hoặc bất biến sâu của phần tử. Nếu cần thứ tự, phải chọn bản sao có hợp đồng thứ tự tương ứng ngay trong thiết kế.

## 11. Ví dụ chạy được: chính sách thay đổi khi sao chép hoặc bọc

Lưu vào `HashSetNullCopyPolicyDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class HashSetNullCopyPolicyDemo {
    public static void main(String[] args) {
        Set<String> source = new HashSet<>();
        source.add("B");
        source.add(null);
        source.add("A");

        Set<String> independent = new HashSet<>(source);
        System.out.println("HashSet copy contains null = "
                + independent.contains(null));

        try {
            Set.copyOf(source);
        } catch (NullPointerException ex) {
            System.out.println("Set.copyOf nullable source = "
                    + ex.getClass().getSimpleName());
        }

        Set<String> readOnlyView = Collections.unmodifiableSet(source);
        System.out.println("read-only view contains null = "
                + readOnlyView.contains(null));

        source.add("C");
        System.out.println("view sees later C = " + readOnlyView.contains("C"));
        System.out.println("independent copy sees later C = "
                + independent.contains("C"));

        try {
            readOnlyView.add("D");
        } catch (UnsupportedOperationException ex) {
            System.out.println("read-only view add = "
                    + ex.getClass().getSimpleName());
        }

        List<String> display = new ArrayList<>(readOnlyView);
        display.sort(Comparator.nullsLast(Comparator.naturalOrder()));
        System.out.println("sorted nullable view = " + display);

        Set<String> concurrent = ConcurrentHashMap.newKeySet();
        try {
            concurrent.add(null);
        } catch (NullPointerException ex) {
            System.out.println("concurrent key set add null = "
                    + ex.getClass().getSimpleName());
        }
    }
}
```
Biên dịch và chạy:

```shell
javac --release 17 HashSetNullCopyPolicyDemo.java
java HashSetNullCopyPolicyDemo
```
Kết quả:

```text
HashSet copy contains null = true
Set.copyOf nullable source = NullPointerException
read-only view contains null = true
view sees later C = true
independent copy sees later C = false
read-only view add = UnsupportedOperationException
sorted nullable view = [A, B, C, null]
concurrent key set add null = NullPointerException
```
Đọc kết quả theo từng hợp đồng:

- Bản sao HashSet nhận null.
- Set.copyOf từ nguồn có null ném NullPointerException.
- Vùng nhìn unmodifiableSet đọc thấy null từ nguồn.
- Thêm C ở nguồn xuất hiện qua vùng nhìn nhưng không xuất hiện trong bản sao độc lập.
- Thử thêm D qua vùng nhìn bị từ chối.
- Danh sách trình bày được sắp rõ ràng với null cuối.
- Tập khóa concurrent trong ví dụ từ chối null.

Chương trình không chạy nhiều luồng; dòng newKeySet chỉ minh họa chính sách null của một cách tạo Set cụ thể.

Bằng cách tách các dòng output về thành viên, quyền sửa và thứ tự trình bày, ví dụ tránh gộp chúng thành một thuộc tính mơ hồ “Set này an toàn hơn” hoặc “Set này tốt hơn”.

## 12. So sánh và kiểm chứng đúng thứ mà hợp đồng bảo đảm

### 12.1. So nội dung tập khi thứ tự không thuộc yêu cầu

Hai Set tuân thủ cùng quan hệ bằng nhau có thể equals nhau dù duyệt khác thứ tự. Muốn kiểm tra có cùng thành viên, dùng hợp đồng Set.equals hoặc các kiểm tra hiện diện/kích thước phù hợp.

Không chuyển cả hai HashSet thành List rồi so List.equals để quyết định nội dung tập có đúng hay không. List.equals có xét vị trí.

Tương tự, toArray hoặc new ArrayList<>(set) chỉ thu các phần tử theo thứ tự gặp được, không tự sắp hoặc khôi phục lịch sử thêm.

### 12.2. Khi thứ tự là yêu cầu, kiểm tra trên đầu ra đã có chính sách

Nếu API đầu ra phải sắp tăng dần và để null cuối, hãy kiểm tra danh sách kết quả sau phép sắp với comparator đã chọn.

Nếu API đầu ra phải giữ thứ tự thêm, hãy giữ nguồn có thứ tự và cấu trúc tương ứng rồi kiểm tra thứ tự đó.

Không kiểm tra một thứ tự mà HashSet chưa từng được yêu cầu cung cấp.

### 12.3. Không dựa vào hình thức in để phân biệt null

Một null và String có nội dung "null" có thể được hiển thị giống nhau khi in một collection thông thường. Điều đó không làm chúng bằng nhau.

Khi chẩn đoán dữ liệu, cần biểu diễn đủ rõ để phân biệt không có tham chiếu với một giá trị văn bản. Ví dụ, có thể dùng dấu trích dẫn cho chuỗi và một ký hiệu riêng cho null trong phần trình bày.

Nhưng ký hiệu trình bày không nên được đưa ngược thành khóa dữ liệu thay cho null nếu điều đó làm va chạm với một chuỗi thật.

### 12.4. Những điều không nên bắt buộc trong bài kiểm tra HashSet

- Không bắt buộc null luôn ở đầu hoặc luôn ở cuối.
- Không bắt buộc hai lần duyệt phải khác nhau.
- Không bắt buộc thêm/xóa một phần tử luôn làm thứ tự đổi.
- Không coi HashSet có cùng nội dung là phải có cùng chuỗi toString.
- Không dùng việc chưa gặp ConcurrentModificationException làm chứng cứ an toàn luồng.

Hợp đồng là cơ sở để chọn điều phải đúng. Một quan sát nội bộ hoặc một lần chạy không mở rộng hợp đồng đó.

## 13. Các lỗi phổ biến và cách sửa mô hình

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Set<String> nghĩa là không thể có null” | Kiểu tham chiếu vẫn có thể nhận null nếu triển khai cho phép |
| “Thêm null hai lần phải tăng size hai lần” | HashSet chỉ giữ một lần hiện diện của null |
| “Tập chỉ có null là tập rỗng” | Nó có một thành viên |
| “null và chuỗi 'null' là cùng dữ liệu” | Chúng khác nhau về giá trị và ý nghĩa |
| “HashSet hỗ trợ null nên mọi hàm xử lý phần tử đều hỗ trợ null” | Phải xem hợp đồng của từng hàm ở phía sau |
| “null có quy ước băm nên chắc chắn đứng đầu khi duyệt” | Không có bảo đảm vị trí đó trong API HashSet |
| “Không có thứ tự nghĩa là mỗi lần phải xáo lại” | Có thể quan sát ổn định nhưng không được dựa vào như hợp đồng |
| “HashSet đang in giống thứ tự thêm nên dùng luôn” | Khi cần thứ tự thêm, chọn cấu trúc có bảo đảm đó |
| “Bọc unmodifiableSet là một bản sao cố định” | Nó là vùng nhìn đọc qua nguồn |
| “Set.copyOf chỉ đổi quyền sửa, không đổi chính sách null” | Nó từ chối phần tử null |
| “Chuyển HashSet thành LinkedHashSet khôi phục lịch nhập” | Chỉ giữ thứ tự gặp được từ nguồn lúc sao chép |
| “Sắp dữ liệu String luôn xử lý null tự động” | Cần comparator hoặc chính sách null phù hợp |
| “Cùng dùng băm thì mọi Set cùng nhận null” | Chính sách thuộc lớp/cách tạo cụ thể |

## 14. Thực hành xác định hợp đồng đầu ra

### Bài 1: Đếm dữ liệu thiếu

Nguồn có null, null, A. Đưa vào HashSet rồi hỏi size không thể cho biết có hai bản ghi thiếu. Tập chỉ biểu diễn hiện diện của null và A. Muốn thống kê số lần thiếu phải giữ hoặc đếm các lần xuất hiện.

### Bài 2: Kết quả in có hai chữ null

Một Set giữ null và String "null" không nhất thiết vi phạm loại trùng dù hình thức in có thể làm chúng giống nhau. Kiểm tra bằng value == null hoặc một định dạng chẩn đoán rõ ràng thay vì chỉ nhìn chữ in ra.

### Bài 3: Cần thứ tự nhập

Nguồn có B, null, A, B. Muốn đầu ra B, null, A theo lần xuất hiện đầu tiên thì dùng cấu trúc giữ thứ tự từ chính nguồn đó. Đừng gom vào HashSet rồi sau đó cố suy lại thứ tự nhập.

### Bài 4: Cần sắp với null cuối

Có các giá trị B, null, A. Tạo bản danh sách và dùng Comparator.nullsLast với quy tắc so các giá trị không null. Kết quả trình bày A, B, null là do comparator, không phải do HashSet vốn có thứ tự đó.

### Bài 5: Cần kết quả không sửa được nhưng null hợp lệ

Set.copyOf không đáp ứng chính sách nhận null. Có thể tạo bản sao riêng bằng cấu trúc cho phép null rồi bọc không sửa được, đồng thời chọn rõ có cần bảo đảm thứ tự hay không. Phần tử có thể sửa vẫn cần chính sách riêng.

### Bài 6: Chuyển sang tập khóa của ConcurrentHashMap

Không được giả định null được giữ chỉ vì cả cấu trúc cũ và mới dùng băm. Cần kiểm tra và quyết định cách xử lý null trước khi chuyển. Chương trình ví dụ đã xác nhận cách tạo newKeySet từ chối thêm null.

### Bài 7: Chọn phần tử đầu

HashSet không rỗng và iterator.next trả một phần tử. Điều đó không chứng minh đây là giá trị nhỏ nhất, giá trị nhập đầu hay một lựa chọn ngẫu nhiên công bằng. Hãy dùng thuật toán tương ứng với mục tiêu thực.

Trước khi dùng một Set dựa trên băm, hãy nêu riêng **null có ý nghĩa gì, collection nào nhận nó, các hàm phía sau xử lý ra sao và đầu ra có cần thứ tự nào**. Hai chính sách về dữ liệu và thứ tự phải được giữ rõ ràng từ đầu vào đến lúc trình bày kết quả.
