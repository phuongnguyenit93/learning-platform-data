# Null-safe selection trong Spring Expression Language

Spring Expression Language (SpEL) hỗ trợ selection để lọc các phần tử của collection theo một điều kiện. Ví dụ, có thể lấy tất cả thành viên mang quốc tịch Serbian bằng biểu thức:

~~~spel
#members.?[nationality == 'Serbian']
~~~

Nếu collection nguồn có thể là null, selection thông thường không thể thực hiện trên đối tượng null. Từ Spring Framework 6.2, SpEL hỗ trợ **null-safe selection** bằng cách đặt toán tử null-safe ngay trước toán tử selection:

~~~spel
#members?.?[nationality == 'Serbian']
~~~

Cần phân biệt chính xác hai cú pháp gần giống nhau:

- **Null-safe selection:** ?.?[...]
- **Null-safe indexing:** ?.[]

Vì vậy, ?.[] là cú pháp indexer an toàn khi lấy một phần tử theo chỉ số hoặc khóa; selection có dấu ngoặc điều kiện cần thêm dấu ? sau toán tử null-safe. Bài này tập trung vào null-safe selection và cách nó xử lý collection có thể null.

## 1. Selection thông thường hoạt động như thế nào?

Selection là thao tác lọc collection. SpEL đánh giá một predicate cho từng phần tử rồi giữ lại những phần tử thỏa điều kiện.

Cú pháp selection tổng quát:

~~~spel
collection.?[condition]
~~~

Ví dụ, giả sử có danh sách thành viên:

~~~java
public class Member {
    private final String name;
    private final String nationality;

    public Member(String name, String nationality) {
        this.name = name;
        this.nationality = nationality;
    }

    public String getName() {
        return name;
    }

    public String getNationality() {
        return nationality;
    }
}
~~~

Tạo collection và đăng ký vào EvaluationContext:

~~~java
List<Member> members = Arrays.asList(
    new Member("Ana", "Serbian"),
    new Member("Mark", "American"),
    new Member("Mila", "Serbian")
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("members", members);
~~~

Selection:

~~~spel
#members.?[nationality == 'Serbian']
~~~

Kết quả là collection gồm Ana và Mila.

Trong predicate:

- SpEL duyệt từng phần tử của collection.
- nationality được đọc trên phần tử đang xét.
- #this tham chiếu phần tử hiện tại.
- Điều kiện trả về Boolean để quyết định phần tử có được giữ lại hay không.

Có thể viết tường minh hơn:

~~~spel
#members.?[#this.nationality == 'Serbian']
~~~

Hai cách viết đều thể hiện việc lọc theo nationality của phần tử hiện tại.

## 2. Vấn đề khi collection nguồn là null

Trong ứng dụng thực tế, collection có thể được lấy từ API, database, cấu hình hoặc một property chưa được khởi tạo. Vì vậy, biến hoặc property đại diện collection có thể mang giá trị null.

Ví dụ:

~~~java
List<Member> members = null;

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("members", members);
~~~

Nếu đánh giá selection thông thường:

~~~spel
#members.?[nationality == 'Serbian']
~~~

SpEL cần duyệt các phần tử của collection, nhưng giá trị #members lại là null. Không có collection để duyệt nên evaluation có thể phát sinh lỗi.

Điều này khác với một collection rỗng:

~~~java
List<Member> members = Collections.emptyList();
~~~

Collection rỗng vẫn là một đối tượng hợp lệ. Selection có thể chạy và trả về một collection rỗng vì không có phần tử nào thỏa predicate.

## 3. Cú pháp null-safe selection ?.?

Null-safe selection sử dụng toán tử null-safe ?. ngay trước toán tử selection ?[]:

~~~spel
#members?.?[nationality == 'Serbian']
~~~

Nếu #members là null, SpEL trả về null và bỏ qua thao tác duyệt collection. Nếu collection tồn tại, SpEL thực hiện selection như bình thường.

Ví dụ:

~~~java
List<Member> members = null;

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("members", members);

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#members?.?[nationality == 'Serbian']"
);

Object result = expression.getValue(context);
System.out.println(result);
~~~

Kết quả:

~~~text
null
~~~

Quá trình xử lý:

1. SpEL đọc biến #members từ EvaluationContext.
2. Giá trị của biến là null.
3. Toán tử ?. nhận biết collection đích null.
4. Selection không được thực hiện.
5. Expression trả về null.

Cú pháp này hữu ích khi dữ liệu nguồn là tùy chọn và ứng dụng muốn tránh lỗi chỉ vì collection chưa được khởi tạo.

## 4. Phân biệt null-safe selection với null-safe indexing

Hai cú pháp có hình thức gần giống nhau nhưng thực hiện hai thao tác khác nhau.

| Mục đích | Cú pháp | Ví dụ |
|---|---|---|
| Lấy phần tử theo chỉ số hoặc khóa | ?.[] | #members?.[0] |
| Lọc tất cả phần tử thỏa điều kiện | ?.?[] | #members?.?[active] |
| Lấy phần tử đầu tiên thỏa điều kiện | ?.^[] | #members?.^[active] |
| Lấy phần tử cuối cùng thỏa điều kiện | ?.$[] | #members?.$[active] |

Ví dụ:

~~~spel
#members?.[0]
~~~

đọc phần tử ở vị trí 0 nếu collection tồn tại.

Trong khi đó:

~~~spel
#members?.?[active]
~~~

lọc collection và trả về các phần tử có active là true.

Do đó, khi nói đến null-safe selection, cú pháp chính xác là ?.?[...], không phải ?.[].

## 5. Các dạng null-safe selection

SpEL có các dạng selection khác nhau. Toán tử null-safe có thể được kết hợp với từng dạng.

### 5.1. Chọn tất cả phần tử phù hợp

Dùng ?[] để lấy tất cả phần tử thỏa predicate:

~~~spel
#members?.?[nationality == 'Serbian']
~~~

Nếu collection null, kết quả là null. Nếu collection tồn tại, kết quả là collection gồm mọi phần tử phù hợp.

### 5.2. Chọn phần tử phù hợp đầu tiên

Dùng ^[] để lấy phần tử đầu tiên thỏa điều kiện:

~~~spel
#members?.^[nationality == 'Serbian']
~~~

Nếu collection null, biểu thức trả về null. Nếu collection tồn tại, SpEL tìm phần tử phù hợp đầu tiên theo thứ tự duyệt.

### 5.3. Chọn phần tử phù hợp cuối cùng

Dùng $[] để lấy phần tử cuối cùng thỏa điều kiện:

~~~spel
#members?.$[nationality == 'Serbian']
~~~

Nếu collection null, biểu thức trả về null. Nếu collection tồn tại, SpEL tìm phần tử phù hợp cuối cùng.

Hai dạng chọn đầu tiên và cuối cùng thường trả về một phần tử đơn lẻ, trong khi selection ?[] trả về tập hợp các phần tử phù hợp.

## 6. Null-safe selection với List

Ví dụ với list có dữ liệu:

~~~java
List<Member> members = Arrays.asList(
    new Member("Ana", "Serbian"),
    new Member("Mark", "American"),
    new Member("Mila", "Serbian")
);

context.setVariable("members", members);

Expression selection = parser.parseExpression(
    "#members?.?[nationality == 'Serbian']"
);

Object result = selection.getValue(context);
~~~

Kết quả là collection gồm hai phần tử Ana và Mila.

Có thể tái sử dụng cùng một Expression khi giá trị biến thay đổi:

~~~java
context.setVariable("members", null);
Object whenNull = selection.getValue(context);

context.setVariable(
    "members",
    Collections.emptyList()
);
Object whenEmpty = selection.getValue(context);
~~~

Hai trường hợp có kết quả khác nhau:

- Khi members là null, null-safe selection trả về null.
- Khi members là list rỗng, selection trả về collection rỗng.

Expression không cần phân tích lại chỉ vì dữ liệu đầu vào thay đổi.

## 7. Null-safe selection với Map

SpEL cũng hỗ trợ selection trên map. Với map, predicate có thể truy cập các thuộc tính key và value của entry hiện tại.

Ví dụ:

~~~java
Map<String, Integer> scores = new LinkedHashMap<>();
scores.put("Ana", 90);
scores.put("Mark", 65);
scores.put("Mila", 95);

context.setVariable("scores", scores);
~~~

Lọc những entry có value từ 80 trở lên:

~~~spel
#scores?.?[value >= 80]
~~~

Selection trên map tạo map mới gồm những entry phù hợp. Trong predicate, value là giá trị của entry hiện tại; key là khóa tương ứng.

Có thể viết rõ qua #this:

~~~spel
#scores?.?[#this.value >= 80]
~~~

Nếu #scores là null, null-safe selection trả về null mà không duyệt map.

Nếu map tồn tại nhưng rỗng, selection trả về map rỗng. Nếu map có dữ liệu nhưng không entry nào phù hợp, kết quả cũng là map rỗng.

## 8. Phần tử collection có thể null

Null-safe selection bảo vệ collection nguồn khi chính collection là null. Nó không tự động bảo vệ từng phần tử bên trong collection.

Ví dụ:

~~~java
List<Member> members = new ArrayList<>();
members.add(null);
members.add(new Member("Ana", "Serbian"));

context.setVariable("members", members);
~~~

Predicate:

~~~spel
#members?.?[nationality == 'Serbian']
~~~

có thể gặp lỗi khi phần tử hiện tại là null và SpEL cố đọc property nationality trên phần tử đó.

Nếu phần tử cũng có thể null, hãy bảo vệ phép truy cập trong predicate:

~~~spel
#members?.?[#this != null && #this.nationality == 'Serbian']
~~~

Toán tử && đánh giá ngắn mạch. Khi #this là null, vế sau không được đánh giá.

Có thể dùng null-safe navigation trong predicate:

~~~spel
#members?.?[#this?.nationality == 'Serbian']
~~~

Như vậy, cần phân biệt hai cấp độ:

- Null-safe selection bảo vệ collection nguồn.
- Null-safe property access trong predicate bảo vệ phần tử hoặc property có thể null.

## 9. Collection rỗng, không có phần tử phù hợp và kết quả null

Ba tình huống này cần được phân biệt:

| Trạng thái nguồn | Selection | Kết quả |
|---|---|---|
| Collection là null | #members?.?[condition] | null |
| Collection tồn tại nhưng rỗng | #members?.?[condition] | Collection rỗng |
| Collection có phần tử nhưng không phần tử nào phù hợp | #members?.?[condition] | Collection rỗng |
| Collection có phần tử phù hợp | #members?.?[condition] | Collection gồm các phần tử phù hợp |

Null-safe selection không biến null thành collection rỗng. Nếu downstream code cần luôn nhận collection, ứng dụng phải chuẩn hóa kết quả null thành collection rỗng hoặc xử lý null ở bước tiếp theo.

Với first selection hoặc last selection, kết quả là phần tử được chọn; nếu không có phần tử phù hợp thì không có phần tử nào để trả về. Do đó, mã sử dụng kết quả nên xử lý trường hợp null tương ứng.

## 10. Null-safe selection trong compound expression

Một biểu thức có thể tiếp tục thao tác trên kết quả selection:

~~~spel
#members?.?[active].size()
~~~

Nếu #members null, selection trả về null. Phần gọi .size() tiếp theo vẫn có thể cố gọi phương thức trên null và gây lỗi.

Nếu kết quả selection có thể null, hãy bảo vệ cả bước tiếp theo:

~~~spel
#members?.?[active]?.size()
~~~

Ở đây:

1. #members?.?[active] bảo vệ collection nguồn.
2. ?.size() bảo vệ lời gọi size trên kết quả selection nếu kết quả là null.

Có thể dùng Elvis để thay kết quả null bằng giá trị mặc định:

~~~spel
#members?.?[active]?.size() ?: 0
~~~

Nếu collection null, biểu thức trả về 0. Nếu collection tồn tại, kết quả là số phần tử active. Nếu selection trả về collection rỗng, size là 0.

Cách viết này cho thấy null-safe operator cần được đặt tại từng điểm có khả năng dereference một giá trị null.

## 11. Phiên bản Spring Framework

Null-safe selection và projection được hỗ trợ từ Spring Framework 6.2. Nếu ứng dụng dùng phiên bản cũ hơn, parser có thể không nhận cú pháp null-safe selection.

Với phiên bản chưa hỗ trợ, có thể kiểm tra null trước khi thực hiện selection:

~~~spel
#members != null ? #members.?[active] : null
~~~

Nếu muốn kết quả là collection rỗng thay vì null, có thể chuẩn hóa trong mã Java hoặc dùng một nhánh thay thế phù hợp với kiểu collection của ứng dụng.

Khi chia sẻ biểu thức giữa nhiều dịch vụ, cần kiểm tra phiên bản Spring Framework của từng dịch vụ để tránh dùng cú pháp không tương thích.

## 12. Ví dụ hoàn chỉnh trong Java

Ví dụ sau lọc các thành viên active, trong đó collection có thể null và một số phần tử cũng có thể null:

~~~java
public class Member {
    private final String name;
    private final boolean active;

    public Member(String name, boolean active) {
        this.name = name;
        this.active = active;
    }

    public String getName() {
        return name;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

Chuẩn bị dữ liệu và context:

~~~java
List<Member> members = new ArrayList<>();
members.add(null);
members.add(new Member("Ana", true));
members.add(new Member("Mark", false));
members.add(new Member("Mila", true));

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("members", members);

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#members?.?[#this != null && #this.active]"
);

Object result = expression.getValue(context);
~~~

Kết quả là collection chứa Ana và Mila.

Nếu thay members thành null và đánh giá lại cùng expression, kết quả là null. Nếu thay bằng list rỗng, kết quả là collection rỗng.

## 13. Những nhầm lẫn thường gặp

**Nhầm lẫn 1: Null-safe selection dùng cú pháp ?.[]**  
?.[] là null-safe indexing. Null-safe selection dùng ?.?[condition].

**Nhầm lẫn 2: Null-safe selection bảo vệ cả phần tử null.**  
Nó bảo vệ collection nguồn. Nếu phần tử có thể null, predicate phải bảo vệ property access trên phần tử.

**Nhầm lẫn 3: Collection null và collection rỗng có cùng kết quả.**  
Collection null làm null-safe selection trả về null; collection rỗng trả về collection rỗng.

**Nhầm lẫn 4: Elvis bắt được lỗi selection.**  
Elvis xử lý giá trị null, không bắt exception phát sinh khi predicate hoặc truy cập phần tử thất bại.

**Nhầm lẫn 5: Dùng selection xong có thể gọi phương thức ngay mà không kiểm tra null.**  
Nếu nguồn null, kết quả selection null. Các bước tiếp theo trong compound expression vẫn cần null-safe navigation nếu có thể nhận null.

## 14. Ghi nhớ

- Selection lọc các phần tử của collection theo predicate.
- Selection thông thường dùng ?[condition].
- Null-safe selection dùng ?.?[condition] và được hỗ trợ từ Spring Framework 6.2.
- ?.[] là null-safe indexer để đọc phần tử theo chỉ số hoặc khóa, không phải null-safe selection.
- Selection trên map tạo map mới gồm các entry phù hợp; predicate có thể dùng key và value.
- Null-safe selection bảo vệ collection nguồn, không tự bảo vệ phần tử null trong collection.
- Collection null cho kết quả null; collection rỗng hoặc không có phần tử phù hợp cho kết quả collection rỗng đối với selection toàn bộ.
- First/last selection trả về phần tử được chọn, vì vậy cần xử lý trường hợp không tìm thấy phần tử.
- Khi nối tiếp property hoặc method call, hãy dùng null-safe navigation tại từng vị trí có thể null.

Khi viết null-safe selection, hãy xác định collection nguồn có thể null hay không, phần tử có thể null hay không, predicate cần đọc property nào và phần còn lại của biểu thức sẽ xử lý kết quả null ra sao.
