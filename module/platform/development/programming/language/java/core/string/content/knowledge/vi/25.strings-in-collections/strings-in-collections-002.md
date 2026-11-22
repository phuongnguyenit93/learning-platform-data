# String trong collection: hợp đồng equals–hashCode và va chạm băm

Khi dùng **String** làm phần tử của **HashSet** hoặc làm khóa của **HashMap**, Java cần biết hai chuỗi có được xem là **cùng một giá trị** hay không. Hai phương thức **equals(Object)** và **hashCode()** phối hợp để trả lời câu hỏi đó. Hiểu đúng hợp đồng của chúng giúp tránh mất khóa, đếm sai phần tử và hiểu nhầm hiện tượng **va chạm băm (hash collision)**.

Một nguyên tắc cần nhớ ngay từ đầu: **cùng hashCode không có nghĩa là hai String bằng nhau; nhưng hai String bằng nhau theo equals bắt buộc có cùng hashCode.**

## 1. String.equals so sánh nội dung, không so sánh địa chỉ

String ghi đè phương thức **equals(Object)** để so sánh **nội dung ký tự**. Hai đối tượng String khác nhau vẫn được xem là bằng nhau nếu chứa cùng dãy đơn vị mã UTF-16 theo đúng thứ tự.

~~~java
String a = new String("java");
String b = "java";

System.out.println(a == b);      // false
System.out.println(a.equals(b));  // true
~~~

Giải thích:

- **a == b** kiểm tra hai tham chiếu có trỏ đến **cùng một đối tượng** hay không; đối tượng được tạo tường minh bằng **new String(...)** khác đối tượng chuỗi literal.
- **a.equals(b)** so sánh nội dung, nên trả về **true**.
- So sánh nội dung của String có **phân biệt chữ hoa/chữ thường**: **"Java".equals("java")** là **false**.
- **"java".equals(null)** là **false**. Nếu tham chiếu có thể null, có thể dùng **Objects.equals(a, b)** để kiểm tra hai giá trị null an toàn.

Cùng nội dung không nhất thiết cùng tham chiếu. Cơ chế *string pool* hoặc **intern()** không làm thay đổi quy tắc so sánh nội dung của equals; không dùng **==** để quyết định hai chuỗi là cùng khóa trong ứng dụng.

## 2. Hợp đồng equals–hashCode là gì?

Mọi lớp Java có thể dùng như khóa trong bộ sưu tập dựa trên băm cần tuân thủ hai nhóm quy tắc.

### 2.1. Những quy tắc cơ bản của equals

Đối với đối tượng khác null và khi trạng thái liên quan không thay đổi:

1. **Phản xạ:** **x.equals(x)** là true.
2. **Đối xứng:** **x.equals(y)** và **y.equals(x)** phải trả về cùng kết quả.
3. **Bắc cầu:** nếu x bằng y và y bằng z, x cũng phải bằng z.
4. **Nhất quán:** khi dữ liệu dùng để so sánh không đổi, gọi lại equals phải cho cùng kết quả.
5. **Với null:** **x.equals(null)** phải là false.

String đã triển khai các quy tắc này. Không cần viết lại equals cho String.

### 2.2. Những quy tắc của hashCode

Hợp đồng của **hashCode()** gồm:

- Trong cùng một lần thực thi ứng dụng, nếu dữ liệu tham gia vào equals không đổi, các lần gọi **hashCode()** trên cùng đối tượng phải trả lại cùng số nguyên.
- **Nếu x.equals(y) là true thì x.hashCode() và y.hashCode() phải bằng nhau.**
- **Nếu x.equals(y) là false, hashCode của chúng được phép bằng nhau.** Hai giá trị khác nhau **không bắt buộc** tạo hai mã băm khác nhau.

Có thể biểu diễn chính xác chiều suy luận:

~~~text
x.equals(y) == true   ⇒   x.hashCode() == y.hashCode()

x.hashCode() == y.hashCode()   ⇏   x.equals(y) == true
~~~

Vế thứ hai là lý do một collection dựa trên băm phải dùng **equals** để phân biệt những đối tượng có cùng mã băm. Nếu chỉ kiểm tra số hash, dữ liệu hợp lệ sẽ bị coi nhầm là trùng lặp.

## 3. String.hashCode hoạt động ra sao?

**String.hashCode()** tạo một giá trị kiểu **int** dựa trên nội dung String. Công thức về mặt ngữ nghĩa có dạng:

~~~text
h = 0
Lặp qua từng đơn vị mã UTF-16 c của chuỗi:
    h = 31 * h + c
Kết quả là h theo số nguyên int 32-bit của Java.
~~~

Với chuỗi rỗng, hashCode bằng **0**. Với String có nội dung bằng nhau, tính toán trên cùng dãy đơn vị mã UTF-16 luôn cho cùng hashCode. Số **31** là hệ số trong thuật toán hashCode do Java định nghĩa cho String.

Ví dụ:

~~~text
"Aa" = 31 × mã('A') + mã('a')
     = 31 × 65 + 97
     = 2112

"BB" = 31 × mã('B') + mã('B')
     = 31 × 66 + 66
     = 2112
~~~

Do giá trị hashCode chỉ là một số **int 32-bit** trong khi số lượng chuỗi có thể tạo ra là vô hạn, chắc chắn tồn tại những chuỗi khác nhau cho cùng mã băm. hashCode cũng có thể âm do tràn số nguyên 32-bit; đây không phải lỗi.

**hashCode không phải định danh duy nhất, không phải dấu vân tay an toàn và không phải hàm băm mật mã.** Không dùng nó để xác nhận dữ liệu không bị thay đổi, tạo ID duy nhất hoặc kiểm chứng tính toàn vẹn cần bảo mật.

## 4. Từ hash code đến phép tìm kiếm thực tế

`HashSet<String>` và `HashMap<String, V>` sử dụng **cả mã băm lẫn phép so sánh tương đương**. Mã băm giúp tìm nhóm ứng viên; `equals` xác nhận khóa chính xác. Do bảng có số bucket hữu hạn, ngay cả **hai hashCode khác nhau** cũng có thể rơi vào cùng bucket; đó là vấn đề triển khai được xử lý bên trong collection. Khi cùng hash mà khác `equals`, cả hai giá trị vẫn phải được phân biệt.

~~~java
Map<String, Integer> map = new HashMap<>();
map.put("Aa", 10);
map.put("BB", 20); // "Aa" và "BB" có cùng hashCode
System.out.println(map.size());      // 2
System.out.println(map.get("Aa"));   // 10
System.out.println(map.get("BB"));   // 20

Set<String> set = new HashSet<>();
System.out.println(set.add("Aa"));   // true
System.out.println(set.add("BB"));   // true
System.out.println(set.add(new String("Aa"))); // false
System.out.println(set.size());      // 2
~~~

`map.put(new String("Aa"), 30)` (nếu gọi tiếp) cập nhật entry `"Aa"` vì `equals` đúng, nhưng không đổi entry `"BB"`. Không phải gọi `hashCode` hoặc tự duyệt bucket trong ứng dụng; `Map`/`Set` đã quy định ngữ nghĩa này. Ví dụ hoàn chỉnh ở phần 6 kiểm tra cả trường hợp trùng nội dung và collision.

## 5. Va chạm băm thực tế: "Aa" và "BB"

Hai String **"Aa"** và **"BB"** có nội dung khác nhau nhưng **hashCode bằng nhau**. Đây là ví dụ va chạm băm ngắn, ổn định và dễ tự kiểm tra:

~~~java
String first = "Aa";
String second = "BB";

System.out.println(first.hashCode()); // 2112
System.out.println(second.hashCode()); // 2112
System.out.println(first.equals(second)); // false
~~~

**Va chạm không làm mất dữ liệu.** HashSet vẫn lưu được cả "Aa" lẫn "BB" vì equals trả về false. HashMap vẫn phân biệt và lấy đúng giá trị cho hai khóa.

Điều này không mâu thuẫn với hợp đồng equals–hashCode. Hợp đồng yêu cầu **bằng nhau thì cùng hashCode**, chứ không hề yêu cầu **cùng hashCode thì bằng nhau**.

Trong Java hiện đại, các bucket có nhiều phần tử va chạm được quản lý bằng cơ chế nội bộ thích hợp; HashMap có thể chuyển những bucket đủ đông sang cấu trúc cây khi thỏa các điều kiện triển khai. Đừng lập trình dựa vào thứ tự duyệt bucket hay giả định tất cả thao tác trong mọi tình huống đều có thời gian hằng số.

## 6. Chương trình Java 17+ hoàn chỉnh

Tạo file **StringHashContractDemo.java**:

~~~java
import java.util.HashMap;
import java.util.HashSet;

public class StringHashContractDemo {
    public static void main(String[] args) {
        String a = new String("java");
        String b = "java";

        System.out.println("same reference: " + (a == b));
        System.out.println("equal content: " + a.equals(b));
        System.out.println("same hash: "
                + (a.hashCode() == b.hashCode()));

        HashSet<String> languages = new HashSet<>();
        System.out.println("add first: " + languages.add(a));
        System.out.println("add equal: " + languages.add(b));
        System.out.println("size: " + languages.size());
        System.out.println("contains: " + languages.contains("java"));

        String first = "Aa";
        String second = "BB";

        System.out.println("collision hashes: "
                + first.hashCode() + " / " + second.hashCode());
        System.out.println("collision equals: "
                + first.equals(second));

        HashMap<String, Integer> counts = new HashMap<>();
        counts.put(first, 1);
        counts.put(second, 2);
        counts.put(new String("Aa"), 3);

        System.out.println("map size: " + counts.size());
        System.out.println("Aa: " + counts.get("Aa"));
        System.out.println("BB: " + counts.get("BB"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac StringHashContractDemo.java
java StringHashContractDemo
~~~

Stdout:

~~~text
same reference: false
equal content: true
same hash: true
add first: true
add equal: false
size: 1
contains: true
collision hashes: 2112 / 2112
collision equals: false
map size: 2
Aa: 3
BB: 2
~~~

Cách đọc kết quả:

- Hai đối tượng **a**, **b** khác tham chiếu, nhưng có nội dung và hashCode giống nhau.
- **HashSet** chỉ nhận phần tử đầu tiên vì lần thêm thứ hai bằng theo equals.
- Hai khóa **"Aa"** và **"BB"** có cùng hashCode nhưng không bằng nhau, nên HashMap vẫn có **hai** entry.
- Lần **put(new String("Aa"), 3)** cập nhật giá trị của khóa tương đương với **"Aa"**, nhưng không tác động đến **"BB"**.
- Ví dụ chỉ lấy dữ liệu bằng khóa tường minh; không dựa vào thứ tự duyệt **HashMap** hay **HashSet** vì thứ tự đó không được bảo đảm.

Đây là minh họa trực tiếp cho việc **hashCode quyết định hướng tra cứu còn equals quyết định sự tương đương của khóa** trong bộ sưu tập dựa trên băm.

## 7. Điều kiện ổn định của khóa sau khi chèn

Khóa nằm trong cấu trúc hash phải giữ nguyên các thông tin quyết định `equals/hashCode` khi còn được lưu. Với kiểu tự định nghĩa có trường mutable, việc sửa trường đó sau `put` có thể làm `get` không tìm thấy khóa dù entry vẫn tồn tại.

`String` tránh được rủi ro này vì nội dung bất biến. Gán `key = key.toUpperCase()` chỉ đổi biến tham chiếu sang một `String` khác; giá trị cũ trong map vẫn nguyên. Nếu cần khóa gồm nhiều thành phần, cân nhắc một value object bất biến có hợp đồng `equals/hashCode` đúng thay vì dùng khóa mutable.

## 8. Phân biệt HashSet, HashMap với các collection khác

Không phải collection nào cũng dùng hashCode để nhận biết trùng lặp:

| Collection | Cách xác định phần tử/khóa | Ảnh hưởng của String.hashCode |
| --- | --- | --- |
| **HashSet<String>** | Hash rồi so sánh equals khi cần | Dùng để tổ chức tra cứu |
| **HashMap<String, V>** | Hash và equals cho khóa | Dùng để tổ chức tra cứu |
| **ArrayList<String>** | **contains**, **indexOf** dựa trên equals | Không dùng hashCode cho các thao tác này |
| **TreeSet<String>** | **compareTo** hoặc Comparator để xác định thứ tự và trùng lặp | Không dùng hashCode để xác định phần tử trùng |
| **TreeMap<String, V>** | **compareTo** hoặc Comparator cho khóa | Không dùng hashCode để xác định khóa trùng |

Với String theo thứ tự tự nhiên, **compareTo** trả về 0 khi nội dung String bằng nhau theo equals. Tuy nhiên nếu truyền Comparator tùy chỉnh, ví dụ **String.CASE_INSENSITIVE_ORDER**, TreeSet có thể coi **"Java"** và **"java"** là cùng một phần tử dù **String.equals** của chúng trả về false. Đây là quy tắc do Comparator chọn, không phải lỗi của hashCode.

Nếu chỉ cần danh sách có thể chứa giá trị lặp, dùng List. Nếu cần tập giá trị duy nhất theo **String.equals**, dùng HashSet. Nếu cần bảng ánh xạ từ String sang giá trị, dùng HashMap. Nếu cần tập/ánh xạ có thứ tự theo Comparator, cân nhắc TreeSet/TreeMap.

## 9. Sự bằng nhau của khóa còn phụ thuộc chính sách dữ liệu

`String.equals` phân biệt hoa/thường, khoảng trắng và cách mã hóa Unicode. Vì vậy `"Java"` và `"java"` là hai khóa theo `HashSet`, mặc dù một `TreeSet` dùng `String.CASE_INSENSITIVE_ORDER` có thể coi chúng là cùng khóa do quy tắc comparator.

~~~java
Set<String> raw = new HashSet<>();
raw.add("Java");
raw.add("java");
System.out.println(raw.size()); // 2
~~~

Khi nghiệp vụ muốn hai biến thể thành một định danh, chuẩn hóa **trước khi lưu và tìm** theo chính sách rõ ràng. `toLowerCase(Locale.ROOT)` là một lựa chọn cho mã kỹ thuật, nhưng chưa bao trùm mọi quy tắc ngôn ngữ/Unicode. Chuẩn hóa dữ liệu không phải một thành phần của thuật toán hash và không chữa va chạm băm. Bài riêng về canonical key xử lý lựa chọn đó cùng việc bảo toàn nhãn hiển thị.

## 10. Những hiểu lầm thường gặp

### "Hash bằng nhau nghĩa là dữ liệu bằng nhau"

**Sai.** "Aa" và "BB" có hashCode 2112 nhưng equals false. Hash collision là điều được cho phép và phải được xử lý. Không viết logic kiểu:

~~~java
// SAI về ngữ nghĩa bằng nhau:
boolean same = a.hashCode() == b.hashCode();
~~~

Khi cần so nội dung, dùng **a.equals(b)** (nếu a chắc chắn không null) hoặc **Objects.equals(a, b)**.

### "Hai String khác đối tượng là hai khóa khác nhau"

**Sai đối với HashMap<String, ...> và HashSet<String>.** Chúng dựa vào equals, không dựa vào **==**. Một String mới chứa đúng nội dung cũ có thể truy vấn hoặc cập nhật entry đã tồn tại.

### "HashSet bỏ mất khóa khi có collision"

**Sai.** HashSet dùng equals để phân biệt những phần tử thực sự khác nhau. Collision có thể gây thêm chi phí tra cứu, nhưng không có nghĩa collection gộp hai String không bằng nhau.

### "String hashCode có thể dùng làm ID duy nhất"

**Sai.** Đầu ra 32-bit không thể đại diện duy nhất cho mọi chuỗi. HashCode không phải ID nghiệp vụ hay checksum bảo mật. Nếu cần ID, sử dụng cơ chế sinh ID hoặc định danh từ dữ liệu phù hợp yêu cầu.

### "Tôi có thể dùng == vì các literal nằm trong string pool"

**Không an toàn.** String lấy từ file, request, phép ghép, hoặc được tạo bằng **new** có thể mang tham chiếu khác dù nội dung bằng nhau. **intern()** là một cơ chế riêng, không nên dùng để thay thế việc so sánh nội dung.

### "HashMap/HashSet sẽ duyệt theo thứ tự thêm vào"

**Không có bảo đảm.** Cơ chế hash và collision không xác lập thứ tự duyệt ổn định. Khi cần giữ thứ tự chèn, cân nhắc **LinkedHashMap/LinkedHashSet**; khi cần sắp xếp theo thứ tự, cân nhắc **TreeMap/TreeSet** với thứ tự phù hợp.

### "Tất cả trường hợp tìm kiếm đều O(1)"

**Không có bảo đảm tuyệt đối.** Với phân bố hash phù hợp và kích thước bảng hợp lý, HashMap/HashSet có hiệu năng tra cứu trung bình rất tốt. Nếu có nhiều khóa rơi vào cùng bucket, thao tác phải xét nhiều ứng viên; Java có các tối ưu nội bộ cho trường hợp dày đặc, nhưng hiệu năng còn tùy dữ liệu và cấu trúc thực tế.

## 11. Cách tự kiểm tra khi gặp lỗi String trong collection

Khi **contains**, **get** hoặc **put** cho kết quả bất ngờ, thử kiểm tra theo trình tự:

1. In giá trị String theo cách thể hiện rõ whitespace, chữ hoa/thường và ký tự ẩn. **"java"** và **"java "** không bằng nhau.
2. Kiểm tra trực tiếp **equals** giữa hai giá trị và so sánh **hashCode** để minh họa. Nếu equals true mà hashCode khác ở hai đối tượng cùng lớp, lớp tự định nghĩa có thể vi phạm hợp đồng; riêng String chuẩn không xảy ra điều này.
3. Xác định collection đang dùng hợp đồng **equals/hashCode** hay **Comparator**. HashMap/HashSet khác TreeMap/TreeSet.
4. Với khóa kỹ thuật, xác định có chuẩn hóa đồng nhất ở lúc ghi và lúc tra cứu không.
5. Tránh kiểm tra lỗi bằng thứ tự duyệt HashMap vì đó không phải thứ tự được cam kết.
6. Kiểm tra giá trị null riêng nếu API cần phân biệt **không có khóa** với **khóa có giá trị null**. Với Map, **containsKey** có thể cho thông tin khác việc chỉ xem kết quả **get**.

Ví dụ nhỏ về sự khác biệt giữa **không có khóa** và **giá trị null**:

~~~java
Map<String, String> map = new HashMap<>();
map.put("present", null);

// map.get("present") == null và map.get("missing") == null
// nhưng map.containsKey("present") == true,
// còn map.containsKey("missing") == false.
~~~

Đây là vấn đề về ngữ nghĩa Map, không phải hash collision, nhưng thường bị nhầm khi debug việc tra cứu bằng String.

## 12. Tự đánh giá kiến thức

Cho ba chuỗi:

~~~java
String a = "Aa";
String b = "BB";
String c = new String("Aa");
~~~

Hãy dự đoán kết quả:

| Biểu thức | Kết quả | Lý do |
| --- | --- | --- |
| **a.hashCode() == b.hashCode()** | true | Cùng mã băm 2112 |
| **a.equals(b)** | false | Nội dung khác nhau |
| **a == c** | false | c là đối tượng tạo mới |
| **a.equals(c)** | true | Cùng nội dung "Aa" |
| **a.hashCode() == c.hashCode()** | true | equals true kéo theo hashCode bằng nhau |

Nếu thêm **a**, **b**, **c** vào một **HashSet<String>**, kích thước cuối là **2**: a và c được coi là cùng giá trị, còn b khác giá trị dù trùng hashCode. Nếu dùng làm khóa HashMap, **put(c, value)** sẽ cập nhật ánh xạ đang ứng với a; b vẫn là khóa riêng.

Hãy ghi nhớ đúng chiều suy luận: **equals bằng nhau ⇒ hashCode bằng nhau; hashCode bằng nhau ⇏ equals bằng nhau**. String đã bảo đảm hợp đồng, còn HashSet/HashMap đã được thiết kế để xử lý va chạm mà vẫn phân biệt các chuỗi thực sự khác nhau.
