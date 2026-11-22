# EnumSet: tập hợp enum và biểu diễn gọn

Một enum định nghĩa một tập hằng hữu hạn, chẳng hạn các chế độ READ, WRITE, EXECUTE, DELETE và SHARE. Một đối tượng có thể chọn không hằng nào, một vài hằng hoặc tất cả. Khi cần giữ một tập con như vậy, EnumSet là cấu trúc chuyên biệt phù hợp để xem xét.

`EnumSet` vẫn có ngữ nghĩa Set: không giữ bản sao trùng lặp và hỗ trợ kiểm tra thành viên, thêm, xóa, hợp, giao, hiệu. Điểm chuyên biệt là mọi phần tử thuộc cùng một kiểu enum; tập hợp biết miền hằng có thể xuất hiện nên có thể biểu diễn tư cách thành viên bằng các bit.

Bài dùng Java 17. Mục tiêu là hiểu mô hình tập con hữu hạn, dùng các factory đúng, giải thích sự gọn của biểu diễn mà không gán số byte cố định, và biết giới hạn về thay đổi dữ liệu, thứ tự và đồng thời.

## 1. Từ một hằng enum đến một tập con

Giả sử có khai báo minh họa:

~~~java
enum Permission {
    READ, WRITE, EXECUTE, DELETE, SHARE
}
~~~

Một biến `Permission` giữ một hằng trong miền ấy. Một `EnumSet<Permission>` giữ tập con của miền: ví dụ READ và DELETE.

~~~text
miền hằng khả dụng:
{READ, WRITE, EXECUTE, DELETE, SHARE}

một tập con:
{READ, DELETE}

tập rỗng:
{}
~~~

Gọi miền hằng khả dụng là U. Nếu U có 5 hằng, số tập con khác nhau là 2^5. Không cần tạo một enum khác cho từng tổ hợp; một EnumSet biểu diễn được lựa chọn tổ hợp trên cùng miền.

### 1.1. Vì sao không dùng nhiều boolean?

Năm boolean riêng có thể dùng được trong một lớp nhỏ, nhưng chúng không tự cung cấp phép hợp/giao, duyệt các lựa chọn đang bật hoặc truyền một tập lựa chọn qua API.

EnumSet đặt những thao tác ấy vào một cấu trúc tập hợp thống nhất. Tên hằng cho biết ý nghĩa; kiểu phần tử giúp trình biên dịch ngăn việc đưa một hằng của enum khác vào cùng tập.

Điều này không có nghĩa mọi boolean đều phải đổi thành EnumSet. Nếu dữ liệu chỉ có một thuộc tính độc lập, boolean vẫn rõ ràng. EnumSet có giá trị khi nhiều hằng cùng một miền được chọn theo dạng tập con.

### 1.2. Một kiểu enum cho mỗi tập

`EnumSet<Permission>` không phải một túi chứa mọi enum bất kỳ. Miền phần tử được xác định khi tạo tập, dù tập đang rỗng.

Các kiểu enum khác nhau có thể có hằng cùng tên READ nhưng vẫn không trở thành cùng miền. Giữ generic đúng giúp tránh trộn chúng bằng raw type hoặc ép kiểu không an toàn.

EnumSet là lớp trừu tượng; mã ứng dụng tạo qua các phương thức factory, không dùng `new EnumSet<>()`. Có thể công bố biến bằng giao diện Set nếu API chỉ cần thao tác tập hợp:

~~~java
Set<Permission> enabled =
        EnumSet.of(Permission.READ, Permission.WRITE);
~~~

Đây là đoạn minh họa một phần. Đối tượng vẫn là EnumSet, nên thứ tự duyệt và các đặc điểm của nó vẫn có hiệu lực. [Java 17: EnumSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html)

## 2. Biểu diễn gọn bằng tư cách thành viên

### 2.1. Mỗi hằng là một vị trí

Với năm hằng, có thể lập mô hình:

~~~text
vị trí:   4       3       2        1      0
hằng:   SHARE   DELETE  EXECUTE   WRITE  READ

tập {READ, DELETE}:
bit:      0       1       0        0      1
~~~

Bit 1 nghĩa là hằng tương ứng thuộc tập; bit 0 nghĩa là không thuộc. Sơ đồ là mô hình giải thích, không phải định dạng mà toString của EnumSet in ra.

Không cần cấp một nút riêng để ghi lại từng lần thêm một hằng đã có. Tư cách thành viên chỉ là có hoặc không, phù hợp với ngữ nghĩa không trùng của Set.

### 2.2. Thao tác tập hợp nối với phép toán bit

Nếu hai tập cùng miền có các vectơ bit tương ứng:

~~~text
A = {READ, DELETE} -> 01001
B = {READ, WRITE}  -> 00011

hợp A ∪ B:        01011 -> READ, WRITE, DELETE
giao A ∩ B:       00001 -> READ
hiệu A \ B:       01000 -> DELETE
~~~

Đây là lý do cấu trúc chuyên biệt có thể xử lý hiệu quả các phép tập hợp trên cùng miền. Ứng dụng vẫn gọi addAll, retainAll và removeAll; không cần tự viết các mặt nạ bit.

Phần bù cần giới hạn trong miền enum:

~~~text
miền 5 hằng:      11111
A:               01001
U \ A:           10110 -> WRITE, EXECUTE, SHARE
~~~

Không được hiểu phần bù là mọi bit của một số nguyên hoặc mọi giá trị Java khác. Miền enum quyết định những thành viên có ý nghĩa.

### 2.3. Gọn không có nghĩa toàn bộ đối tượng chỉ vài byte

API mô tả EnumSet dùng vectơ bit. Trong mã factory của OpenJDK 17, miền không quá 64 hằng được chọn triển khai RegularEnumSet; miền lớn hơn được chọn JumboEnumSet. Quyết định này dựa vào số hằng của kiểu enum, không phải chỉ số thành viên hiện đang được chọn. [OpenJDK 17: EnumSet.java](https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/java.base/share/classes/java/util/EnumSet.java)

Hai điểm cần giữ:

- EnumSet không bị giới hạn tối đa 64 hằng enum.
- Không nên dựa vào tên lớp triển khai riêng để quyết định nghiệp vụ hoặc ép kiểu.

Mô hình bit cho thấy một miền lớn hơn có thể cần nhiều nhóm bit để biểu diễn. Nhưng tổng bộ nhớ còn có đối tượng tập, thông tin kiểu và các tham chiếu liên quan; không được nói “cả EnumSet luôn chỉ tốn 8 byte”.

Cũng không phải mỗi tập tạo lại toàn bộ đối tượng hằng enum. Các hằng enum là những đối tượng đã có của kiểu; cấu trúc đang biểu diễn những hằng nào thuộc tập.

Muốn có số byte hoặc thời gian chính xác cần môi trường và phép đo cụ thể. Bài không dùng các kết quả in tên thành viên để suy ra tốc độ hay dung lượng bộ nhớ.

## 3. Tạo tập theo ý định

| Factory | Ý nghĩa |
|---|---|
| noneOf(Permission.class) | Tập rỗng nhưng biết rõ miền Permission |
| allOf(Permission.class) | Tất cả hằng của Permission |
| of(READ, WRITE, ...) | Chọn rõ các hằng |
| range(WRITE, DELETE) | Các hằng từ WRITE đến DELETE theo thứ tự khai báo, gồm hai đầu |
| copyOf(enumSet) | Tập mới cùng kiểu và cùng thành viên ban đầu |
| copyOf(collection) | Suy miền theo hợp đồng nguồn Collection |
| complementOf(enumSet) | Tập mới gồm các hằng cùng miền chưa có trong nguồn |

Factory tạo ra EnumSet có thể thay đổi thành viên. Tên `of` không làm nó có cùng tính chất bất biến như `Set.of`.

### 3.1. Tập rỗng phải biết kiểu

Đoạn minh họa:

~~~java
EnumSet<Permission> selected =
        EnumSet.noneOf(Permission.class);
~~~

Dù chưa có phần tử nào để nhìn vào, tập đã biết miền Permission. Vì vậy sau đó có thể thêm READ, hoặc tạo phần bù là toàn bộ Permission.

Không có dạng `EnumSet.of()` không đối số để thay cho noneOf. Dùng class token là cách nói rõ miền khi chưa chọn hằng nào.

### 3.2. Of không giữ trùng và không giữ thứ tự chèn

`EnumSet.of(DELETE, READ, READ)` chỉ có READ và DELETE. Thêm READ một lần nữa trả false vì tập không đổi.

Factory này khác `Set.of` ở việc đối số trùng không bị dùng như lỗi khai báo tập bất biến. Tuy nhiên, không nên đưa trùng để cố ghi lại số lần hoặc mức ưu tiên. Nếu cần số lần, bài toán không còn chỉ là một Set.

### 3.3. Range gồm cả hai đầu

Với thứ tự READ, WRITE, EXECUTE, DELETE, SHARE:

~~~text
range(WRITE, DELETE) -> WRITE, EXECUTE, DELETE
range(READ, READ)    -> READ
~~~

Range theo thứ tự khai báo, không theo tên chữ cái và không theo trường số riêng bên trong enum. Truyền đầu đứng sau cuối ném IllegalArgumentException.

Nó tạo tập thành viên ban đầu, không tạo một cửa sổ tự động cập nhật theo một tập nguồn khác. Đừng mang trực giác view của một số cấu trúc có thứ tự sang factory range của EnumSet.

## 4. CopyOf và trường hợp nguồn rỗng

### 4.1. Một EnumSet rỗng vẫn giữ miền

CopyOf nhận một EnumSet có thể sao chép ngay cả khi nguồn rỗng. Miền phần tử đã là thông tin của tập.

Trường hợp Collection cần đọc kỹ: nếu đối tượng nguồn thực sự là một EnumSet, factory Collection xử lý như sao chép EnumSet. Điều đó vẫn đúng khi biến nguồn được khai báo bằng Collection.

Ví dụ minh họa:

~~~java
Collection<Permission> source =
        EnumSet.noneOf(Permission.class);

EnumSet<Permission> copy = EnumSet.copyOf(source);
copy.add(Permission.READ);
~~~

Không nên kết luận chỉ từ kiểu biến Collection rằng nguồn rỗng luôn thất bại.

### 4.2. Collection rỗng thông thường không cho biết miền để suy

Với một List rỗng không phải EnumSet, `EnumSet.copyOf(list)` ném IllegalArgumentException. Factory không có phần tử để suy miền mới theo hợp đồng của nó.

Đây không phải việc “EnumSet không hỗ trợ tập rỗng”. NoneOf và copy từ EnumSet rỗng đã cho thấy tập rỗng hoàn toàn hợp lệ.

Nếu API biết kiểu và chấp nhận một Collection có thể rỗng, có thể tạo noneOf trước rồi addAll:

~~~java
EnumSet<Permission> result =
        EnumSet.noneOf(Permission.class);
result.addAll(input);
~~~

Đoạn này là minh họa với input đã có, không null và chỉ chứa phần tử hợp lệ. Nó xác định miền độc lập với việc input có thành viên hay không.

Hợp đồng copyOf(Collection) phân biệt rõ nguồn EnumSet và nguồn thông thường rỗng. [Java 17: các factory copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html)

### 4.3. Sao chép độc lập về thành viên

CopyOf và clone tạo tập mới; thêm hoặc xóa ở tập nguồn về sau không tự làm đổi thành viên của bản sao.

Các phần tử vẫn là những hằng enum tương ứng, không phải các bản clone mới. Nếu một enum được thiết kế có trạng thái có thể thay đổi bên trong, sao chép tập không tự sao chép trạng thái đó.

Trong thiết kế thông thường, nên để ý nghĩa các hằng và dữ liệu đi kèm ổn định. Cấu trúc tập hợp không tự quản lý tính bất biến của mọi đối tượng mà nó tham chiếu.

## 5. Duyệt theo thứ tự khai báo

EnumSet duyệt các thành viên theo thứ tự tự nhiên của enum, tức thứ tự hằng được khai báo. Không phải thứ tự thêm và không phải thứ tự chữ cái.

Với Permission trong bài:

~~~text
of(SHARE, WRITE, READ)
duyệt -> READ, WRITE, SHARE
~~~

EnumSet không phải SortedSet và không nhận một comparator riêng để đổi thứ tự duyệt của nó. Nếu cần một thứ tự hiển thị khác, hãy tạo một danh sách kết quả và sắp xếp theo yêu cầu, thay vì giả định đổi tên hằng sẽ thay cách tổ chức mong muốn.

Thứ tự khai báo cũng là cơ sở cho compareTo và ordinal của Enum. Ordinal bắt đầu từ 0, phản ánh vị trí khai báo; API mô tả nó chủ yếu phục vụ các cấu trúc chuyên biệt như EnumSet và EnumMap. [Java 17: Enum](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html)

### 5.1. Không tự dùng ordinal như mã lưu trữ bền vững

Nếu thêm một hằng vào giữa hoặc đổi thứ tự khai báo, các vị trí có thể thay đổi. Một số bit tự lưu ra bên ngoài theo ordinal có thể được diễn giải sai sau thay đổi phiên bản.

Ứng dụng cần định dạng lưu trữ hoặc trao đổi phải thiết kế định danh ổn định phù hợp. Không biến mô hình nội bộ của EnumSet thành giao thức tự chế chỉ vì nó gọn trong một phiên bản enum.

Tên hằng hoặc mã tường minh cũng cần chính sách tương thích khi đổi tên hoặc thêm giá trị; điểm chính là tách thiết kế dữ liệu ngoài hệ thống khỏi vị trí khai báo trong mã nguồn.

### 5.2. AllOf và complementOf phụ thuộc miền hiện tại

Khi thêm một hằng mới vào enum rồi chạy phiên bản mới, allOf chứa cả hằng mới. ComplementOf cũng xét miền mới, không chỉ danh sách hằng từng tồn tại trong phiên bản cũ.

Nếu một tập biểu diễn các khả năng được cho phép, “tất cả trừ vài hằng” khác với “chỉ các hằng đã liệt kê”. Hãy chọn factory theo chính sách nghiệp vụ, không chỉ theo độ ngắn của mã.

Đây là hệ quả của mô hình tập con hữu hạn: thay U có thể thay kết quả U trừ A ngay cả khi danh sách A giữ nguyên.

## 6. Các phép tập hợp và việc thay đổi đối tượng nhận

Các thao tác quen thuộc từ Set vẫn có ý nghĩa:

| Phương thức | Ngữ nghĩa |
|---|---|
| add(e) | Thêm thành viên nếu chưa có |
| remove(e) | Loại thành viên nếu có |
| contains(e) | Kiểm tra một thành viên |
| addAll(B) | Biến tập nhận A thành A hợp B |
| retainAll(B) | Biến tập nhận A thành A giao B |
| removeAll(B) | Biến tập nhận A thành A trừ B |
| containsAll(B) | Hỏi B có là tập con của A không |
| clear() | Loại toàn bộ thành viên |

Ba phép cập nhật hàng loạt sửa chính đối tượng nhận. Nếu muốn giữ A và B, sao chép A rồi áp thao tác lên bản sao.

Ví dụ minh họa:

~~~java
EnumSet<Permission> allowed =
        EnumSet.of(Permission.READ, Permission.DELETE);
EnumSet<Permission> required =
        EnumSet.of(Permission.READ, Permission.WRITE);

EnumSet<Permission> missing = EnumSet.copyOf(required);
missing.removeAll(allowed);
~~~

Missing là WRITE: những yêu cầu chưa nằm trong allowed. Nếu làm ngược `allowed.removeAll(required)`, kết quả sẽ là các phần cho phép không nằm trong yêu cầu, một câu hỏi khác.

Phép hiệu không có tính đổi chỗ. Đặt tên biến giúp người đọc hiểu tập nào đang bị trừ.

### 6.1. ContainsAll hỏi đủ, không hỏi có giao hay không

Nếu required có READ và WRITE, allowed chỉ có READ thì containsAll trả false. Có một thành viên chung chưa đủ.

Nếu muốn hỏi “có ít nhất một phần chung không?”, đó là câu hỏi giao khác rỗng. Không thay thế nó bằng containsAll.

### 6.2. Ngữ nghĩa Set vẫn được giữ

EnumSet có thể bằng một Set triển khai khác nếu có cùng các thành viên theo hợp đồng Set. Không cần hai đối tượng có cùng tên lớp để tập hợp bằng nhau.

Ngược lại, thứ tự in khác nhau không làm hai tập khác nội dung. Đừng so các chuỗi toString để thay cho equals của Set. [Java 17: Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

## 7. Null, tính có thể sửa và quyền sở hữu

### 7.1. Không cho thêm null

Thêm null vào EnumSet ném NullPointerException. Contains(null) và remove(null) hoạt động bình thường và không tìm thấy phần tử null.

Điều này giúp phân biệt “không chọn hằng nào” với “thêm một phần tử null”. Muốn biểu diễn không có lựa chọn, dùng tập rỗng.

Cũng không gán null cho cả biến EnumSet rồi mong các thao tác tập rỗng vẫn dùng được. Biến tham chiếu null và một tập rỗng có miền là hai trạng thái khác nhau.

### 7.2. Final không khóa thành viên

Một trường final tham chiếu EnumSet ngăn gán lại tham chiếu, không ngăn add hoặc remove trên đối tượng ấy. Nếu công bố nó trực tiếp, bên nhận có thể thay đổi thành viên khi có quyền gọi các phương thức sửa.

Nếu mục đích chỉ đọc, có thể trả một lớp bọc không sửa được. Nhưng lớp bọc và bản sao cần được phân biệt.

### 7.3. View chỉ đọc và bản chụp độc lập

Ví dụ:

~~~java
Set<Permission> view = Collections.unmodifiableSet(owner);

Set<Permission> snapshot =
        Collections.unmodifiableSet(EnumSet.copyOf(owner));
~~~

View không cho bên nhận sửa qua view, nhưng vẫn phản ánh thay đổi thành viên của owner. Snapshot bọc một bản sao nên không theo các lần add/remove về sau trên owner.

Cần giữ quyền kiểm soát đối tượng bản sao bên trong nếu muốn nó không tiếp tục bị sửa qua một tham chiếu khác. Đây là vấn đề quyền sở hữu dữ liệu, không chỉ tên phương thức unmodifiable.

Lớp bọc unmodifiableSet là một góc nhìn chỉ đọc qua chính lớp bọc, không tự tách khỏi nguồn. [Java 17: Collections.unmodifiableSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set))

## 8. Iterator và truy cập đồng thời

Iterator của EnumSet là loại nhất quán yếu: không ném ConcurrentModificationException và có thể có hoặc không phản ánh thay đổi trong lúc duyệt theo hợp đồng của lớp.

Không suy ra từ đó rằng EnumSet an toàn cho nhiều luồng. Nó không tự đồng bộ hóa; nếu nhiều luồng cùng truy cập và có sửa đổi, cần cơ chế bảo vệ bên ngoài phù hợp. [Java 17: chính sách iterator của EnumSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html)

Hai kết luận nên tránh:

- “Không có ngoại lệ nên cập nhật cạnh tranh đúng.”
- “Iterator chắc chắn là ảnh chụp đầy đủ và bất biến của mọi EnumSet.”

Ví dụ chương trình không cố dự đoán chính xác một lịch sửa đổi trong lúc duyệt. Nó dùng iterator.remove để minh họa xóa một thành viên theo lượt duyệt đơn luồng rõ ràng.

Nếu cần đọc một bộ lựa chọn ổn định, có thể dùng bản sao được tạo trong trạng thái được bảo vệ đúng. Việc sao chép giữa lúc nguồn bị sửa không có cơ chế phối hợp không tự giải quyết vấn đề.

## 9. Khi nào nên chọn EnumSet?

EnumSet là ứng viên tự nhiên khi dữ liệu là tập con của một enum cụ thể và cần thao tác thành viên hoặc phép tập hợp.

Nó không thay thế mọi Set:

| Yêu cầu | Điều cần cân nhắc |
|---|---|
| Tập hằng của cùng một enum | EnumSet phù hợp để xem xét |
| Mã hoặc tên được thêm động lúc chạy | Không phải miền enum hữu hạn đã khai báo |
| Giữ thứ tự chèn | EnumSet duyệt theo thứ tự khai báo, cần cấu trúc khác nếu thứ tự chèn quan trọng |
| Sắp theo comparator riêng | EnumSet không có comparator tùy chọn |
| Lưu số lần hoặc nhiều bản sao | Set không biểu diễn tần suất |
| Chia sẻ nhiều luồng có cập nhật | Cần thiết kế đồng thời, không suy từ biểu diễn bit |

Biểu diễn chuyên biệt thường tạo lợi thế về cấu trúc và thao tác. Không dùng câu “luôn nhanh hơn mọi Set” như một bảo đảm cho mọi chương trình. Tổng chi phí còn phụ thuộc dữ liệu, tần suất sao chép, cách dùng và môi trường.

Một enum có hơn 64 hằng vẫn dùng được. Chương trình cố ý tạo miền 65 hằng rồi chỉ chọn ba hằng ở các vị trí khác nhau để bác bỏ nhầm lẫn “EnumSet chỉ hỗ trợ 64 phần tử enum”.

## 10. Chương trình Java đầy đủ

Lưu mã sau vào `EnumSetCompactDemo.java`. Các enum nằm trong lớp để tệp có thể biên dịch trực tiếp mà không cần tạo thêm tệp nguồn.

Chương trình kiểm chứng ngữ nghĩa thành viên, thứ tự duyệt, các phép tập hợp, sao chép nguồn rỗng, null, quyền sửa và miền lớn. Nó không truy cập các trường riêng của JDK hoặc đo số byte.

~~~java
import java.util.Collection;
import java.util.Collections;
import java.util.EnumSet;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Set;

public class EnumSetCompactDemo {
    enum Permission {
        READ, WRITE, EXECUTE, DELETE, SHARE
    }

    enum Wide {
        F00, F01, F02, F03, F04, F05, F06, F07, F08, F09,
        F10, F11, F12, F13, F14, F15, F16, F17, F18, F19,
        F20, F21, F22, F23, F24, F25, F26, F27, F28, F29,
        F30, F31, F32, F33, F34, F35, F36, F37, F38, F39,
        F40, F41, F42, F43, F44, F45, F46, F47, F48, F49,
        F50, F51, F52, F53, F54, F55, F56, F57, F58, F59,
        F60, F61, F62, F63, F64
    }

    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected enum set result");
        }
    }

    private static <E extends Enum<E>> EnumSet<E> copyKnownType(
            Class<E> type, Collection<E> source) {
        EnumSet<E> result = EnumSet.noneOf(type);
        result.addAll(source);
        return result;
    }

    public static void main(String[] args) {
        EnumSet<Permission> empty = EnumSet.noneOf(Permission.class);
        System.out.println("empty=" + empty);

        EnumSet<Permission> selected =
                EnumSet.of(Permission.DELETE, Permission.READ, Permission.READ);
        boolean duplicateAdded = selected.add(Permission.READ);
        require(selected.size() == 2 && !duplicateAdded);
        System.out.println("selected=" + selected
                + ", duplicateAdded=" + duplicateAdded);
        System.out.println("order=" + EnumSet.of(
                Permission.SHARE, Permission.WRITE, Permission.READ));
        System.out.println("all=" + EnumSet.allOf(Permission.class));
        System.out.println("complement=" + EnumSet.complementOf(selected));

        EnumSet<Permission> range =
                EnumSet.range(Permission.WRITE, Permission.DELETE);
        System.out.println("range=" + range);
        boolean reverseRangeRejected = false;
        try {
            EnumSet.range(Permission.DELETE, Permission.WRITE);
        } catch (IllegalArgumentException exception) {
            reverseRangeRejected = true;
        }
        require(reverseRangeRejected);
        System.out.println("range/reversedRejected=" + reverseRangeRejected);

        EnumSet<Permission> required =
                EnumSet.of(Permission.READ, Permission.WRITE);
        EnumSet<Permission> union = EnumSet.copyOf(selected);
        union.addAll(required);
        EnumSet<Permission> intersection = EnumSet.copyOf(selected);
        intersection.retainAll(required);
        EnumSet<Permission> difference = EnumSet.copyOf(selected);
        difference.removeAll(required);
        require(union.equals(EnumSet.of(
                Permission.READ, Permission.WRITE, Permission.DELETE)));
        require(intersection.equals(EnumSet.of(Permission.READ)));
        require(difference.equals(EnumSet.of(Permission.DELETE)));
        System.out.println("algebra/union=" + union);
        System.out.println("algebra/intersection=" + intersection);
        System.out.println("algebra/difference=" + difference);
        System.out.println("algebra/containsRequired="
                + selected.containsAll(required));

        EnumSet<Permission> copy = EnumSet.copyOf(selected);
        selected.add(Permission.SHARE);
        require(!copy.contains(Permission.SHARE));
        System.out.println("copy/source=" + selected + ", copy=" + copy);

        boolean emptyListRejected = false;
        try {
            EnumSet.copyOf(List.<Permission>of());
        } catch (IllegalArgumentException exception) {
            emptyListRejected = true;
        }
        require(emptyListRejected);
        System.out.println("copy/emptyListRejected=" + emptyListRejected);
        Collection<Permission> emptyEnumSet =
                EnumSet.noneOf(Permission.class);
        EnumSet<Permission> fromEnumSet = EnumSet.copyOf(emptyEnumSet);
        fromEnumSet.add(Permission.READ);
        System.out.println("copy/emptyEnumSetAsCollection=" + fromEnumSet);
        System.out.println("copy/knownTypeEmpty="
                + copyKnownType(Permission.class, List.<Permission>of()));

        boolean nullRejected = false;
        try {
            selected.add(null);
        } catch (NullPointerException exception) {
            nullRejected = true;
        }
        require(nullRejected);
        System.out.println("null/addRejected=" + nullRejected
                + ", contains=" + selected.contains(null)
                + ", remove=" + selected.remove(null));

        EnumSet<Permission> removable = EnumSet.copyOf(range);
        Iterator<Permission> iterator = removable.iterator();
        while (iterator.hasNext()) {
            if (iterator.next() == Permission.EXECUTE) {
                iterator.remove();
            }
        }
        require(removable.equals(EnumSet.of(
                Permission.WRITE, Permission.DELETE)));
        System.out.println("iterator/afterRemove=" + removable);
        System.out.println("equality/hashSet=" + copy.equals(
                new HashSet<>(List.of(Permission.READ, Permission.DELETE))));

        EnumSet<Permission> owner = EnumSet.of(Permission.READ);
        Set<Permission> view = Collections.unmodifiableSet(owner);
        Set<Permission> snapshot =
                Collections.unmodifiableSet(EnumSet.copyOf(owner));
        owner.add(Permission.WRITE);
        System.out.println("ownership/view=" + view + ", snapshot=" + snapshot);
        boolean viewAddRejected = false;
        try {
            view.add(Permission.DELETE);
        } catch (UnsupportedOperationException exception) {
            viewAddRejected = true;
        }
        require(viewAddRejected);
        System.out.println("ownership/addRejected=" + viewAddRejected);

        EnumSet<Wide> wide = EnumSet.of(Wide.F64, Wide.F00, Wide.F63);
        require(wide.size() == 3 && wide.contains(Wide.F64));
        require(EnumSet.allOf(Wide.class).size() == 65);
        require(EnumSet.complementOf(wide).size() == 62);
        System.out.println("wide/members=" + wide + ", size=" + wide.size());
        System.out.println("wide/universe=" + Wide.values().length
                + ", complementSize=" + EnumSet.complementOf(wide).size());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 EnumSetCompactDemo.java
java EnumSetCompactDemo
~~~

Stdout của lần chạy kiểm chứng:

~~~text
empty=[]
selected=[READ, DELETE], duplicateAdded=false
order=[READ, WRITE, SHARE]
all=[READ, WRITE, EXECUTE, DELETE, SHARE]
complement=[WRITE, EXECUTE, SHARE]
range=[WRITE, EXECUTE, DELETE]
range/reversedRejected=true
algebra/union=[READ, WRITE, DELETE]
algebra/intersection=[READ]
algebra/difference=[DELETE]
algebra/containsRequired=false
copy/source=[READ, DELETE, SHARE], copy=[READ, DELETE]
copy/emptyListRejected=true
copy/emptyEnumSetAsCollection=[READ]
copy/knownTypeEmpty=[]
null/addRejected=true, contains=false, remove=false
iterator/afterRemove=[WRITE, DELETE]
equality/hashSet=true
ownership/view=[READ, WRITE], snapshot=[READ]
ownership/addRejected=true
wide/members=[F00, F63, F64], size=3
wide/universe=65, complementSize=62
~~~

Mã đã được biên dịch với `--release 17` và chạy thành công. Tùy chọn release xác định mức API và mã đích tương thích; không khẳng định JVM thực thi là đúng bản JDK 17.

## 11. Đọc kết quả theo từng ý nghĩa

### 11.1. Thành viên và thứ tự

Selected chỉ có READ và DELETE dù READ xuất hiện lặp trong factory. Add READ trả false. Dòng order có thứ tự READ, WRITE, SHARE dù đối số được đưa theo SHARE, WRITE, READ.

Các kết quả ấy thuộc ngữ nghĩa tập và thứ tự khai báo, không phải một phép sắp theo tên hoặc lịch sử thêm.

### 11.2. Phần bù, range và các phép toán

Complement gồm WRITE, EXECUTE, SHARE vì đó là phần của miền năm hằng chưa có trong selected ban đầu. Range WRITE đến DELETE gồm cả WRITE và DELETE.

Phép hợp, giao và hiệu đều được tính trên bản sao nên không phá tập nguồn trước khi nó còn được dùng để đối chiếu. ContainsRequired trả false vì selected thiếu WRITE.

### 11.3. Sao chép và nguồn rỗng

Source được thêm SHARE sau khi copy; copy vẫn chỉ có READ và DELETE. List rỗng bị copyOf từ chối, còn đối tượng EnumSet rỗng được khai báo qua Collection vẫn sao chép được.

CopyKnownType nhận class token để xử lý nguồn rỗng thông thường. Nó chọn miền trước rồi mới thêm các thành viên nguồn.

### 11.4. Null và quyền sửa

Add null bị từ chối; contains/remove null đều false. View chỉ đọc phản ánh owner có thêm WRITE, trong khi snapshot vẫn chỉ có READ. Lần thêm qua view bị từ chối.

Không có mâu thuẫn giữa “view không cho sửa” và “nội dung view thay đổi”: người sở hữu đã sửa nguồn mà view đang đọc xuyên tới.

### 11.5. Miền 65 hằng

Wide có 65 hằng; tập chọn F00, F63, F64 có ba thành viên và được duyệt theo thứ tự khai báo. AllOf có 65 thành viên, phần bù của tập ba thành viên có 62.

Kết quả chứng minh hành vi API vượt miền 64 hằng. Nó không chứng minh một kích thước bộ nhớ cụ thể và không yêu cầu ứng dụng biết đang dùng lớp triển khai riêng nào.

## 12. Những lỗi thường gặp

| Lỗi | Cách hiểu đúng |
|---|---|
| EnumSet chứa mọi kiểu enum lẫn nhau | Mỗi tập có một miền enum cụ thể |
| Tập rỗng là tham chiếu null | NoneOf tạo đối tượng rỗng biết miền |
| Of luôn tạo tập không sửa được | EnumSet.of trả tập có thể sửa thành viên |
| Thêm hằng trùng tạo bản sao | Set chỉ có tư cách thành viên có/không |
| EnumSet giữ thứ tự thêm | Nó duyệt theo thứ tự khai báo enum |
| Range loại đầu cuối như một khoảng nửa mở | EnumSet.range gồm cả hai đầu |
| CopyOf mọi Collection rỗng đều được | Nguồn thông thường rỗng không cho suy miền |
| CopyOf Collection rỗng luôn lỗi | Nguồn thực sự là EnumSet vẫn giữ thông tin miền |
| Complement là đảo mọi bit vô hạn | Phần bù nằm trong miền enum |
| AddAll hoặc retainAll không sửa tập nguồn nhận | Chúng cập nhật đối tượng nhận |
| Final làm tập bất biến | Nó không cấm add/remove trên đối tượng |
| UnmodifiableSet tự tạo bản sao | Nó là view chỉ đọc; muốn tách thành viên cần copy |
| Không ném CME nghĩa là an toàn đồng thời | Chính sách iterator không thay thế đồng bộ hóa |
| EnumSet bị giới hạn 64 hằng | API hỗ trợ miền lớn hơn |
| Gọn nghĩa là cả đối tượng luôn chỉ 8 byte | Biểu diễn bit không phải tổng bố cục đối tượng |
| Ordinal phù hợp làm mã bền vững mặc định | Nó gắn với vị trí khai báo và cần tách khỏi giao thức ngoài |

## 13. Thực hành và lời giải

### Bài 1. Tập hợp hay danh sách?

Cần giữ ba chế độ enum, không có phần tử trùng và thường hỏi có bật một chế độ không. EnumSet phù hợp ở đâu? Nếu cần ghi số lần chế độ xuất hiện thì sao?

**Lời giải:** EnumSet phù hợp với tập con của một enum và các thao tác tư cách thành viên. Nếu cần số lần, Set không chứa thông tin tần suất; phải thiết kế cấu trúc đếm phù hợp.

### Bài 2. Đọc thứ tự

Enum khai báo A, B, C, D. Tạo of(D, B, A) rồi thêm B lần nữa. Duyệt theo thứ tự nào, size bằng bao nhiêu và add B trả gì?

**Lời giải:** A, B, D; size bằng ba; add B trả false vì tập đã có B. Thứ tự khai báo quyết định đường duyệt.

### Bài 3. Hợp, giao, hiệu

A có READ, DELETE; B có READ, WRITE. Hãy tính A hợp B, A giao B và A trừ B. Có thể gọi removeAll trên A mà vẫn giữ nguyên A cho tác vụ sau không?

**Lời giải:** Hợp là READ, WRITE, DELETE; giao là READ; hiệu là DELETE. RemoveAll sửa chính tập nhận, nên cần sao chép A trước nếu muốn giữ A nguyên vẹn.

### Bài 4. Copy nguồn rỗng

Một hàm nhận Collection có thể là List rỗng hoặc EnumSet rỗng. Vì sao copyOf không có cùng kết quả cho hai đối tượng? Nếu hàm biết kiểu Permission, cách xử lý ổn định là gì?

**Lời giải:** EnumSet giữ miền phần tử ngay khi rỗng; Collection thông thường rỗng không cung cấp phần tử để factory suy miền. Có thể tạo noneOf(Permission.class) rồi addAll nguồn hợp lệ. Kiểu biến Collection không làm mất việc đối tượng nguồn thực sự là EnumSet.

### Bài 5. Giữ dữ liệu chỉ đọc

Owner là EnumSet có READ. Tạo unmodifiableSet(owner), sau đó owner thêm WRITE. View có thấy WRITE không? Làm gì nếu cần bản thành viên tách khỏi cập nhật của owner?

**Lời giải:** View thấy WRITE vì đọc xuyên tới owner. Nếu cần tách thành viên, sao chép owner rồi bọc bản sao, đồng thời không để một tham chiếu khác tiếp tục sửa bản sao ngoài ý định.

### Bài 6. Thêm hằng mới

Enum trước đây có A, B, C; A được chọn. Sang phiên bản mới thêm D. AllOf và complementOf tập chỉ có A thay đổi thế nào? Điều đó ảnh hưởng gì tới ý định “cho phép mọi khả năng trừ A”?

**Lời giải:** AllOf có A, B, C, D; phần bù có B, C, D. Hằng mới tự nằm trong các kết quả dựa trên toàn miền. Cần phân biệt chính sách liệt kê rõ với chính sách mọi hằng trừ một số hằng.

### Bài 7. Tại sao không tự dùng int?

Một người muốn thay EnumSet bằng int và tự gán bit theo ordinal để lưu ra tệp. Hãy nêu hai vấn đề ngoài việc viết được phép AND/OR.

**Lời giải:** Cần bảo đảm đúng miền và tránh trộn cờ của các enum khác, đồng thời phải có định dạng tương thích khi thêm hoặc đổi thứ tự hằng. Ordinal là vị trí khai báo; không tự là mã bền vững. Một int còn có giới hạn bit riêng không giống khả năng hỗ trợ miền lớn của EnumSet.

### Bài 8. Không có ngoại lệ khi duyệt

Một chương trình sửa EnumSet trong lúc duyệt và không có ConcurrentModificationException. Có đủ để kết luận cập nhật nhiều luồng đúng không?

**Lời giải:** Không. Iterator của EnumSet vốn không ném ngoại lệ đó theo hợp đồng và chỉ có tính nhất quán yếu. Cần thiết kế đồng thời và bảo vệ trạng thái đúng; không dùng sự vắng ngoại lệ làm bằng chứng.

## 14. Tự kiểm tra mô hình

Hãy xác định miền enum, tập thành viên hiện tại và ai có quyền sửa tập. Sau đó chọn factory, phép tập hợp và cách công bố kết quả theo đúng ba thông tin ấy.

Biểu diễn bit giải thích vì sao EnumSet là cấu trúc chuyên biệt gọn. API Set giúp ứng dụng thao tác bằng tên hằng và ý nghĩa tập hợp, còn các giới hạn về thứ tự, sao chép và đồng thời vẫn cần được hiểu rõ để dùng đúng.
