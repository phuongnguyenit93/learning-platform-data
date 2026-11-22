# Collection lồng nhau và nhiều tầng xử lý

## Mục tiêu

Trong Spring Expression Language (SpEL), collection operations cho phép lọc hoặc chuyển đổi các phần tử ngay trong biểu thức. Khi một phần tử lại chứa collection khác, có thể lồng selection và projection để xử lý nhiều cấp dữ liệu. Ví dụ, một trường học có nhiều lớp, mỗi lớp có nhiều học sinh; một cửa hàng có nhiều đơn hàng, mỗi đơn hàng có nhiều dòng sản phẩm.

Khi xử lý collection lồng nhau, điều quan trọng là hiểu phạm vi của **#this**, vai trò ổn định của **#root**, kiểu kết quả sau mỗi bước và cách xử lý collection null hoặc rỗng. Một biểu thức nhiều tầng có thể ngắn, nhưng nếu không theo dõi được từng bước, việc bảo trì và chẩn đoán lỗi sẽ khó khăn.

Sau bài này, bạn có thể:

- Lồng selection và projection trên collection nhiều cấp.
- Theo dõi #this khi chuyển từ collection ngoài sang collection bên trong.
- Dùng #root và biến EvaluationContext để đưa dữ liệu chung vào nhiều tầng xử lý.
- Kết hợp lọc, chuyển đổi và truy cập thuộc tính theo từng bước.
- Dự đoán kiểu và cấu trúc kết quả của biểu thức lồng nhau.
- Xử lý collection null, collection rỗng và phần tử không hợp lệ.
- Biết khi nào nên chuyển phần xử lý phức tạp sang Java.

## 1. Mô hình dữ liệu nhiều cấp

Hãy dùng ví dụ một trường học có nhiều lớp, mỗi lớp có danh sách học sinh:

~~~java
public class Student {
    private String name;
    private int score;
    private boolean active;

    public String getName() { return name; }
    public int getScore() { return score; }
    public boolean isActive() { return active; }
}

public class SchoolClass {
    private String className;
    private List<Student> students;

    public String getClassName() { return className; }
    public List<Student> getStudents() { return students; }
}

public class School {
    private List<SchoolClass> classes;

    public List<SchoolClass> getClasses() { return classes; }
}
~~~

Cấu trúc dữ liệu có ba cấp:

1. School là root object.
2. School chứa nhiều SchoolClass.
3. Mỗi SchoolClass chứa nhiều Student.

Một biểu thức có thể bắt đầu từ School, đi qua classes, rồi tiếp tục thao tác trên students. Mỗi cấp có kiểu phần tử riêng, vì vậy cần biết collection hiện tại chứa object nào trước khi viết điều kiện.

Ví dụ, để lấy danh sách lớp:

~~~text
#root.classes
~~~

Để lấy danh sách học sinh của lớp đầu tiên:

~~~text
#root.classes[0].students
~~~

Để lọc học sinh trong lớp đầu tiên có điểm ít nhất 80:

~~~text
#root.classes[0].students.?[score >= 80]
~~~

Đây là một selection ở cấp học sinh. Khi cần xử lý tất cả lớp, ta có thể lồng thao tác vào projection hoặc selection ở cấp ngoài.

## 2. Phạm vi của #this trong collection lồng nhau

**#root** luôn đại diện cho root object được truyền vào khi đánh giá biểu thức. **#this** đại diện cho object hiện tại trong ngữ cảnh đang được đánh giá.

Khi một collection operation lặp qua phần tử, #this chuyển sang phần tử hiện tại của operation đó. Nếu trong điều kiện hoặc projection lại có một collection operation khác, operation bên trong tạo phạm vi hiện tại cho các phần tử của collection bên trong.

Ví dụ:

~~~text
#root.classes.![students.?[active]]
~~~

Có thể đọc biểu thức theo từng bước:

1. #root.classes lấy danh sách lớp từ School.
2. Projection .![...] chạy một lần cho mỗi SchoolClass.
3. Trong mỗi lần projection, students là danh sách học sinh của lớp hiện tại.
4. Selection .?[active] chạy trên danh sách học sinh đó; #this lúc này là Student đang được xét.
5. Selection trả về các học sinh active của lớp hiện tại.

Kết quả là một danh sách các danh sách học sinh. Mỗi danh sách bên trong tương ứng với một lớp.

Có thể viết rõ #this ở cả hai cấp:

~~~text
#root.classes.![#this.students.?[#this.active]]
~~~

Ở projection ngoài, #this là SchoolClass. Bên trong selection trên students, #this là Student. Khi operation bên trong hoàn tất, biểu thức tiếp tục trong phạm vi projection ngoài.

### #root vẫn giữ nguyên

Ngay cả khi #this đang là Student trong selection lồng nhau, #root vẫn là School ban đầu:

~~~text
#root.classes.![students.?[score >= #root.minimumScore]]
~~~

Ví dụ này giả định root object cung cấp property minimumScore. Mỗi học sinh được so sánh với cùng ngưỡng ở School.

Nếu giá trị ngưỡng đến từ cấu hình, có thể truyền nó qua biến:

~~~text
#root.classes.![students.?[score >= #minimumScore]]
~~~

Biến #minimumScore được cung cấp trong EvaluationContext và có thể dùng ở mọi tầng của biểu thức.

## 3. Lồng selection để lọc collection ngoài dựa trên collection trong

Một trường hợp phổ biến là chọn object ở cấp ngoài nếu collection con của nó có ít nhất một phần tử thỏa điều kiện.

Ví dụ, lấy các lớp có ít nhất một học sinh đang active:

~~~text
#root.classes.?[students.?[active].size() > 0]
~~~

Cách đọc:

1. Selection ngoài duyệt từng SchoolClass.
2. Trong mỗi lớp, selection bên trong lọc students có active là true.
3. size() lấy số học sinh được chọn.
4. Nếu số lượng lớn hơn 0, lớp hiện tại được giữ lại.

Ở selection ngoài, #this là SchoolClass. Trong selection bên trong, #this là Student. Khi phép selection bên trong hoàn thành, kết quả size được dùng để quyết định có giữ SchoolClass hiện tại hay không.

Có thể viết điều kiện tường minh hơn:

~~~text
#root.classes.?[#this.students.?[#this.active].size() > 0]
~~~

### Lọc theo số lượng tối thiểu

Nếu cần ít nhất hai học sinh đạt điều kiện:

~~~text
#root.classes.?[students.?[active and score >= #minimumScore].size() >= 2]
~~~

Biểu thức chỉ giữ các lớp có ít nhất hai học sinh vừa active vừa đạt minimumScore.

Cách làm này phù hợp với điều kiện đếm đơn giản. Nếu cần nhiều phép tổng hợp, nhóm dữ liệu, sắp xếp hoặc tính toán phức tạp trên từng lớp, hãy cân nhắc xử lý bằng Java để dễ kiểm thử và tối ưu.

## 4. Lồng projection để chuyển đổi nhiều cấp

Projection dùng **.![ ]** để chuyển mỗi phần tử thành kết quả của biểu thức bên trong. Nếu kết quả bên trong lại là một collection, projection ngoài giữ collection đó như một phần tử kết quả.

Ví dụ, lấy tên học sinh active của từng lớp:

~~~text
#root.classes.![students.?[active].![name]]
~~~

Kết quả có dạng:

~~~text
[
  ["Lan", "An"],
  ["Minh"],
  ["Hoa", "Nam", "Mai"]
]
~~~

Mỗi danh sách con là tên học sinh active của một lớp. Đây là cấu trúc lồng nhau; projection không tự động ghép tất cả tên thành một danh sách phẳng.

Có thể chuyển đổi sang điểm số thay vì tên:

~~~text
#root.classes.![students.?[active].![score]]
~~~

Kết quả có cấu trúc List<List<Integer>> nếu score là kiểu int được đóng gói thành Integer trong collection kết quả.

### Giữ thêm dữ liệu ở cấp ngoài

Có thể lấy tên lớp và danh sách học sinh bằng nhiều phép chiếu, nhưng cần chú ý mỗi projection tạo ra một cấu trúc kết quả riêng. Ví dụ, lấy danh sách tên lớp:

~~~text
#root.classes.![className]
~~~

Và danh sách tên học sinh theo từng lớp:

~~~text
#root.classes.![students.![name]]
~~~

Nếu cần trả về một cấu trúc kết hợp có tên lớp cùng danh sách học sinh trong một object kết quả, thường nên tạo DTO trong Java thay vì cố ghép hai projection độc lập thành một cấu trúc phức tạp trong SpEL.

## 5. Kết hợp selection và projection qua nhiều tầng

Selection và projection có thể nối tiếp nhau. Một quy trình thường gặp là lọc collection ngoài, lọc collection trong, rồi chuyển các phần tử còn lại thành giá trị cần dùng.

Ví dụ, lấy tên học sinh active có điểm từ ngưỡng trở lên, theo từng lớp:

~~~text
#root.classes.![students.?[active and score >= #minimumScore].![name]]
~~~

Các bước:

1. Projection ngoài duyệt từng lớp.
2. Selection trong giữ học sinh active và đạt ngưỡng.
3. Projection trong chuyển mỗi Student còn lại thành name.
4. Projection ngoài thu các danh sách tên theo từng lớp.

Kết quả là một List<List<String>>.

Nếu chỉ muốn các lớp có ít nhất một học sinh đạt điều kiện, có thể lọc lớp trước:

~~~text
#root.classes.?[students.?[active and score >= #minimumScore].size() > 0].![students.?[active and score >= #minimumScore].![name]]
~~~

Biểu thức này có hai giai đoạn rõ ràng:

- Selection ngoài loại bỏ các lớp không có học sinh đạt điều kiện.
- Projection ngoài tạo danh sách tên học sinh đạt điều kiện cho mỗi lớp còn lại.

Điều kiện bên trong xuất hiện hai lần. Nếu logic đó trở nên dài hoặc dễ bị sửa lệch giữa các vị trí, hãy chuyển quy tắc thành một phương thức Java có tên rõ ràng hoặc chuẩn bị dữ liệu đã lọc trước khi đánh giá.

## 6. Collection lồng nhau trong Map

Map có thể chứa value là một collection. Khi selection chạy trên Map, #this đại diện cho entry hiện tại; key và value có thể được truy cập qua entry.

Giả sử root object chứa Map từ tên nhóm tới danh sách học sinh:

~~~java
Map<String, List<Student>> groups;
~~~

Để giữ các entry có ít nhất một học sinh active:

~~~text
#root.groups.?[#this.value.?[active].size() > 0]
~~~

Ở selection ngoài, #this là Map.Entry. Trong selection bên trong trên value, #this là Student. Kết quả selection ngoài vẫn là Map để giữ key và value của các nhóm được chọn.

Lấy danh sách tên học sinh active theo từng entry:

~~~text
#root.groups.![value.?[active].![name]]
~~~

Kết quả là một danh sách các danh sách tên, theo thứ tự duyệt của Map. Vì projection trên Map tạo kết quả dựa trên các value được duyệt, nếu cần giữ key bên cạnh danh sách con, hãy tạo cấu trúc kết quả rõ ràng trong Java hoặc dùng một quy ước biểu thức có thể kiểm thử.

Với Map không bảo đảm thứ tự, không nên dựa vào vị trí của phần tử trong kết quả. Nếu thứ tự có ý nghĩa, chọn implementation Map có quy tắc ordering phù hợp.

## 7. Nhiều tầng collection và kiểu kết quả

Khi lồng nhiều collection operation, hãy dự đoán kiểu kết quả sau mỗi tầng. Điều này giúp tránh giả định rằng kết quả luôn là một List phẳng.

| Biểu thức | Kiểu kết quả khái quát |
|---|---|
| **#root.classes** | List<SchoolClass> |
| **#root.classes.?[condition]** | List<SchoolClass> đã lọc |
| **#root.classes.![students]** | List<List<Student>> |
| **#root.classes.![students.?[active]]** | List<List<Student>> |
| **#root.classes.![students.?[active].![name]]** | List<List<String>> |
| **#root.classes.?[students.?[active].size() > 0]** | List<SchoolClass> |

Các kiểu cụ thể có thể phụ thuộc vào collection nguồn và kiểu giá trị được projection trả về. Hãy yêu cầu kiểu kết quả rõ ràng ở Java khi gọi getValue nếu ứng dụng cần một kiểu xác định.

### Selection không làm phẳng collection

Ví dụ:

~~~text
#root.classes.![students.?[active].![name]]
~~~

Không trả về một List<String> duy nhất. Nó trả về một danh sách chứa danh sách tên theo từng lớp.

Nếu yêu cầu nghiệp vụ là một danh sách phẳng gồm mọi tên học sinh active, SpEL collection projection không tự động thực hiện flatMap. Có thể thực hiện bước flatten trong Java sau khi lấy kết quả lồng nhau, hoặc chuẩn bị một collection phẳng trong service trước khi đánh giá biểu thức.

Đừng dựa vào việc ép kiểu để làm phẳng cấu trúc. Ép kiểu chỉ thay đổi cách Java nhìn nhận kết quả, không thay đổi các collection con bên trong.

## 8. Null và collection rỗng ở từng tầng

Collection lồng nhau có thể null ở nhiều vị trí:

- Collection ngoài null, ví dụ classes null.
- Một phần tử ngoài null, ví dụ một SchoolClass null trong classes.
- Collection con null, ví dụ students null trong một lớp.
- Phần tử trong null, ví dụ một Student null.
- Property dùng trong predicate null.

Cần phân biệt collection null với collection rỗng. Collection rỗng không có phần tử để lọc và thường cho kết quả selection rỗng. Collection null không thể duyệt bằng selection thông thường.

Từ Spring Framework 6.2, SpEL hỗ trợ null-safe selection và projection. Ví dụ:

~~~text
#root.classes?.![students?.?[active]]
~~~

Nếu classes null, projection null-safe trả về null. Nếu một lớp có students null, selection null-safe trên students trả về null cho vị trí tương ứng.

Null-safe operation chỉ xử lý target null tại vị trí toán tử được đặt. Nó không tự xử lý phần tử null bên trong collection hoặc property không tồn tại. Nếu collection có thể chứa phần tử null, hãy kiểm tra phần tử trước khi truy cập property:

~~~text
#root.students.?[#this != null and #this.active]
~~~

Với nested collection, đặt điều kiện bảo vệ tại đúng tầng:

~~~text
#root.classes.?[#this != null and #this.students != null and #this.students.?[#this != null and #this.active].size() > 0]
~~~

Biểu thức trên chỉ giữ lớp không null, có students không null và có ít nhất một học sinh không null đang active. Nếu biểu thức trở nên quá dài, hãy chuyển xác thực và lọc cơ bản sang Java.

Hãy xác nhận phiên bản Spring Framework trước khi sử dụng cú pháp null-safe collection operation; các dạng null-safe selection/projection được bổ sung trong Spring Framework 6.2.

## 9. Dùng biến chung trong nhiều tầng xử lý

Biến trong EvaluationContext có thể được tham chiếu ở mọi tầng của biểu thức. Điều này hữu ích khi nhiều selection cùng dùng một ngưỡng hoặc một mã trạng thái.

Ví dụ:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable("minimumScore", 80);
context.setVariable("requiredStatus", "ACTIVE");
~~~

Biểu thức:

~~~text
#root.classes.![students.?[active and score >= #minimumScore].![name]]
~~~

Cả selection trên students đều sử dụng cùng minimumScore.

Có thể truyền biến cho điều kiện trạng thái:

~~~text
#root.classes.![students.?[status == #requiredStatus].![name]]
~~~

Dùng biến giúp tránh nhúng giá trị cấu hình vào chuỗi biểu thức. Nó cũng giúp kiểm thử cùng một expression với nhiều ngưỡng hoặc chính sách khác nhau.

Nên ghi lại tên và kiểu biến mà mỗi biểu thức yêu cầu. Nếu biến bị thiếu hoặc có kiểu không phù hợp, lỗi sẽ xuất hiện khi đánh giá một tầng có sử dụng biến đó.

## 10. Chia biểu thức phức tạp thành các bước dễ hiểu

Một biểu thức lồng nhau dài có thể hợp lệ nhưng khó đọc. Khi có nhiều tầng selection/projection, hãy viết lại theo từng bước để xác định kết quả trung gian.

Ví dụ mục tiêu: lấy tên học sinh active đạt điểm từ 80 trở lên ở mọi lớp.

Bước 1 — lấy danh sách lớp:

~~~text
#root.classes
~~~

Bước 2 — lấy học sinh đạt điều kiện trong một lớp:

~~~text
#root.classes[0].students.?[active and score >= 80]
~~~

Bước 3 — lấy tên của các học sinh đạt điều kiện trong lớp đó:

~~~text
#root.classes[0].students.?[active and score >= 80].![name]
~~~

Bước 4 — áp dụng cho mọi lớp:

~~~text
#root.classes.![students.?[active and score >= 80].![name]]
~~~

Mỗi bước làm rõ kiểu dữ liệu và phạm vi #this. Nếu một bước không trả về kết quả như mong đợi, có thể kiểm tra riêng collection, predicate hoặc projection tương ứng.

Nếu cần nhiều bước xử lý không thể diễn đạt ngắn gọn, hãy cân nhắc:

- Tạo method Java có tên thể hiện nghiệp vụ.
- Tách một quy tắc lớn thành các expression nhỏ có tên.
- Tính collection trung gian trong service rồi truyền vào SpEL.
- Dùng DTO để giữ cấu trúc kết quả nhiều cấp.
- Viết unit test cho từng bước thay vì một biểu thức khổng lồ.

SpEL phù hợp với điều kiện và biến đổi dữ liệu có cấu trúc rõ ràng. Logic cần grouping, sorting, aggregation nhiều kiểu hoặc xử lý lỗi chi tiết thường dễ bảo trì hơn trong Java.

## 11. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| #this tham chiếu sai object | Đang ở trong selection/projection lồng nhau | Xác định operation gần nhất và kiểu phần tử hiện tại |
| #root không trỏ tới collection con | Nhầm root object với phần tử hiện tại | Dùng đường dẫn từ #this cho object hiện tại, giữ #root cho root ban đầu |
| Kết quả có nhiều List con | Projection lồng nhau giữ cấu trúc collection | Xác định có cần nested result hay cần flatten trong Java |
| Selection ngoài trả rỗng | Predicate trong hoặc ngoài không khớp | Kiểm tra từng predicate trên dữ liệu đại diện |
| Lỗi khi đọc property ở tầng trong | Phần tử con null hoặc sai kiểu | Kiểm tra collection con và kiểu phần tử |
| Lỗi khi gọi size() | Kết quả selection null hoặc collection nguồn không hợp lệ | Xác định null-safe behavior và kiểm tra collection |
| Thứ tự kết quả không ổn định | Collection nguồn không bảo đảm thứ tự | Chọn List hoặc Map có ordering rõ ràng |
| Biểu thức khó bảo trì | Quá nhiều tầng hoặc lặp điều kiện | Tách bước hoặc chuyển logic sang Java |

Khi chẩn đoán, bắt đầu từ collection ngoài, sau đó kiểm tra từng tầng. Đừng sửa cả biểu thức cùng lúc nếu chưa xác định tầng nào tạo ra kết quả sai.

## 12. Kiểm thử collection lồng nhau

Kiểm thử nên xác nhận cấu trúc kết quả, không chỉ số lượng phần tử cuối cùng.

Ví dụ kiểm tra danh sách tên học sinh active theo từng lớp:

~~~java
@Test
void selectsActiveStudentNamesByClass() {
    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression(
        "#root.classes.![students.?[active].![name]]");

    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    School school = sampleSchool();

    List<?> result = expression.getValue(context, school, List.class);

    assertEquals(2, result.size());
    assertEquals(List.of("Lan", "An"), result.get(0));
}
~~~

Bài kiểm thử xác nhận có hai danh sách con và kiểm tra nội dung danh sách đầu tiên. Trong test thực tế, hãy tạo fixture có nhiều lớp với số học sinh và trạng thái khác nhau để kiểm tra cả nhánh rỗng.

Các trường hợp nên có:

| Trường hợp | Điều cần xác minh |
|---|---|
| Nhiều collection con | Mỗi collection con được xử lý độc lập |
| Collection con rỗng | Kết quả ở tầng đó rỗng |
| Collection con null | Hành vi lỗi hoặc null-safe đúng hợp đồng |
| Phần tử con null | Predicate không vô tình dereference null |
| Không phần tử nào khớp | Selection trả collection rỗng |
| Nhiều phần tử khớp | Giữ đúng số lượng và thứ tự |
| Predicate dùng biến ngoài | Biến có mặt và đúng kiểu |
| Lồng selection trong projection | #this chuyển đúng theo tầng |
| Lồng selection trong selection | Điều kiện ngoài nhận đúng kết quả trong |
| Map chứa collection | Key/value và kiểu kết quả được giữ đúng |
| Projection nhiều tầng | Cấu trúc List lồng nhau đúng như dự kiến |
| Yêu cầu flatten | Bước Java làm phẳng cho kết quả đúng |

Hãy dùng cùng loại EvaluationContext và cấu trúc root object như production. Nếu ứng dụng dùng custom PropertyAccessor, hãy tạo context từ cùng factory trong test.

## 13. Thực hành tốt

- Viết biểu thức theo từng tầng từ root tới collection con.
- Dùng #this để làm rõ phần tử đang được xử lý trong operation hiện tại.
- Dùng #root cho dữ liệu chung ở root object và biến context cho cấu hình.
- Phân biệt selection với projection ở từng tầng.
- Dự đoán kiểu kết quả sau mỗi projection; collection lồng nhau không tự flatten.
- Xác định rõ collection null, collection rỗng và phần tử null.
- Dùng null-safe selection/projection khi phiên bản Spring hỗ trợ và null là tình huống được chấp nhận.
- Tránh lặp lại một predicate dài ở nhiều tầng; chuyển thành method hoặc chuẩn bị dữ liệu trong Java khi phù hợp.
- Không gọi method có tác dụng phụ trong selection/projection.
- Chọn collection có thứ tự ổn định khi kết quả phụ thuộc vị trí.
- Kiểm thử từng bước trung gian và cấu trúc kết quả cuối cùng.
- Chuyển grouping, sorting, aggregation phức tạp hoặc flattening sang Java khi biểu thức trở nên khó đọc.

## 14. Checklist review

Trước khi chấp nhận biểu thức collection nhiều tầng, hãy kiểm tra:

- [ ] Root object và các collection con đã được xác định.
- [ ] Kiểu phần tử tại mỗi tầng đã rõ.
- [ ] #this được hiểu theo collection operation hiện tại.
- [ ] #root được dùng cho dữ liệu gốc, không nhầm với phần tử hiện tại.
- [ ] Mỗi selection có predicate Boolean rõ ràng.
- [ ] Mỗi projection có kiểu kết quả dự kiến.
- [ ] Kết quả nested List/Map được giữ hay cần flatten đã được xác định.
- [ ] Collection null, collection rỗng và phần tử null được phân biệt.
- [ ] Null-safe operation phù hợp với phiên bản Spring đang chạy.
- [ ] Thứ tự nguồn được bảo đảm nếu nghiệp vụ phụ thuộc thứ tự.
- [ ] Biểu thức không chứa logic phức tạp có thể chuyển sang Java.
- [ ] Có kiểm thử cho từng tầng và cấu trúc kết quả cuối.

## Kết luận

Collection lồng nhau trong SpEL được xử lý bằng cách kết hợp selection và projection theo từng tầng. Mỗi collection operation có phạm vi #this riêng cho phần tử đang xét, trong khi #root vẫn đại diện cho object gốc. Projection lồng nhau giữ cấu trúc collection con và không tự động làm phẳng kết quả. Khi viết biểu thức nhiều tầng, hãy xác định kiểu dữ liệu và kết quả sau từng bước, xử lý null có chủ đích, dùng biến cho điều kiện chung và chuyển logic quá phức tạp sang Java để dễ kiểm thử và bảo trì.
