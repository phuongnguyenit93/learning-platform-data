# Kiểm thử selection, projection và null-safe navigation trong SpEL

Spring Expression Language (SpEL) cung cấp các phép toán selection và projection để lọc hoặc biến đổi phần tử trong collection. Null-safe navigation giúp expression xử lý những object hoặc collection có thể null mà không phát sinh lỗi truy cập null ở vị trí được bảo vệ.

Các tính năng này thường xuất hiện cùng nhau trong biểu thức đọc dữ liệu lồng nhau. Vì vậy, test cần xác nhận không chỉ giá trị trả về mà còn hình dạng collection, thứ tự phần tử, hành vi với phần tử null, collection null và property trung gian null. Bài học này trình bày cách xây dựng test có dữ liệu rõ ràng để kiểm tra các hành vi đó.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Kiểm thử selection bằng các toán tử .?[], .^[] và .$[].
- Kiểm thử projection bằng toán tử .![].
- Xác nhận selection giữ phần tử nguồn còn projection tạo collection kết quả.
- Kiểm thử selection và projection trên List và Map.
- Kiểm thử null-safe property navigation bằng dấu ?.
- Kiểm thử null-safe selection và projection trên Spring Framework 6.2 trở lên.
- Phân biệt collection null, collection rỗng và collection chứa phần tử null.
- Kiểm tra property lồng nhau có thể null ở từng tầng.
- Viết unit test cho giá trị, kiểu kết quả, thứ tự và lỗi runtime.
- Dùng guard tương thích khi ứng dụng chạy trên phiên bản Spring chưa hỗ trợ null-safe collection operator.

Bạn nên biết cách tạo SpelExpressionParser, Expression, EvaluationContext, JavaBean property và các phép collection operation trong SpEL.

## 2. Selection và projection cần kiểm thử điều gì?

Selection lọc các phần tử của collection theo predicate. Projection áp dụng một expression lên từng phần tử và thu các giá trị được tạo thành collection kết quả.

| Thao tác | Cú pháp | Kết quả điển hình |
|---|---|---|
| Selection tất cả phần tử phù hợp | .?[condition] | Collection chứa các phần tử gốc được giữ lại |
| Selection phần tử phù hợp đầu tiên | .^[condition] | Phần tử đầu tiên thỏa điều kiện |
| Selection phần tử phù hợp cuối cùng | .$[condition] | Phần tử cuối cùng thỏa điều kiện |
| Projection | .![expression] | Collection chứa kết quả expression cho từng phần tử |

Ví dụ:

~~~text
#members.?[active]
~~~

lọc các member có active là true.

~~~text
#members.![name]
~~~

lấy name của từng member và tạo collection kết quả.

Với List nguồn, selection giữ lại các object gốc phù hợp và projection tạo một List các giá trị. Với Map, selection giữ các entry phù hợp và trả Map; projection đánh giá trên từng Map.Entry và trả List kết quả. Test nên kiểm tra đúng kiểu và cấu trúc này thay vì chỉ kiểm tra một chuỗi hiển thị.

## 3. Chuẩn bị dữ liệu kiểm thử

Dùng fixture nhỏ, có tên và trạng thái dễ nhận biết. Ví dụ:

~~~java
public class Member {
    private final String name;
    private final boolean active;
    private final Address address;

    public Member(String name, boolean active, Address address) {
        this.name = name;
        this.active = active;
        this.address = address;
    }

    public String getName() {
        return name;
    }

    public boolean isActive() {
        return active;
    }

    public Address getAddress() {
        return address;
    }
}

public class Address {
    private final String city;

    public Address(String city) {
        this.city = city;
    }

    public String getCity() {
        return city;
    }
}

public class MemberInput {
    private final List<Member> members;

    public MemberInput(List<Member> members) {
        this.members = members;
    }

    public List<Member> getMembers() {
        return members;
    }
}
~~~

Tạo dữ liệu:

~~~java
Member an = new Member(
    "An", true, new Address("Hanoi"));

Member binh = new Member(
    "Binh", false, new Address("Da Nang"));

Member chi = new Member(
    "Chi", true, null);

MemberInput input =
    new MemberInput(List.of(an, binh, chi));
~~~

Fixture này có:

- Hai member active và một member inactive.
- Property address có cả trường hợp khác null và null.
- Dữ liệu đủ nhỏ để đọc rõ kết quả mong đợi.
- Thứ tự phần tử xác định để kiểm tra selection đầu/cuối và thứ tự projection.

Với test phần tử null, không dùng List.of vì factory này không chấp nhận phần tử null. Có thể dùng Arrays.asList hoặc một ArrayList có thể chứa null.

## 4. Tạo parser và đánh giá expression trong test

Một parser có thể được dùng để parse expression trong mỗi test:

~~~java
private final ExpressionParser parser =
    new SpelExpressionParser();
~~~

Ví dụ đọc collection từ root object:

~~~java
Expression expression =
    parser.parseExpression("members.?[active]");

List<?> result =
    expression.getValue(input, List.class);
~~~

Property members được đọc từ root object MemberInput. Trong predicate, property active được phân giải trên phần tử hiện tại.

Nếu dùng variable thay cho root property, đăng ký biến trong context:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("members", members);

List<?> result = parser
    .parseExpression("#members.?[active]")
    .getValue(context, List.class);
~~~

Dùng cùng một cách cung cấp dữ liệu trong mỗi nhóm test để kết quả dễ hiểu. Khi cần test collection null, dùng root DTO có property trả về null hoặc một wrapper nullable. Với StandardEvaluationContext, setVariable(name, null) có thể loại bỏ tên biến khỏi context, nên không dùng cách đó để mô phỏng một biến đã đăng ký với giá trị null.

## 5. Kiểm thử selection trên List

Ví dụ expression:

~~~text
members.?[active]
~~~

Test có thể xác nhận chỉ member active được giữ lại:

~~~java
@Test
void selectsOnlyActiveMembers() {
    List<?> result = parser
        .parseExpression("members.?[active]")
        .getValue(input, List.class);

    assertThat(result)
        .extracting("name")
        .containsExactly("An", "Chi");
}
~~~

Các điều cần xác nhận:

- Số phần tử kết quả đúng.
- Các phần tử được giữ đúng theo predicate.
- Thứ tự tương ứng với thứ tự collection nguồn.
- Selection trả các object nguồn, không tạo object mới cho từng phần tử.

Nên có cả trường hợp không phần tử nào thỏa điều kiện. Với collection nguồn là List không rỗng nhưng predicate luôn false, kết quả là List rỗng, không phải null.

## 6. Kiểm thử selection đầu tiên và cuối cùng

SpEL có hai biến thể selection hữu ích:

~~~text
members.^[active]
~~~

~~~text
members.$[active]
~~~

Biểu thức đầu lấy phần tử đầu tiên thỏa predicate; biểu thức thứ hai lấy phần tử cuối cùng thỏa predicate.

Với fixture An, Binh, Chi:

- Selection đầu tiên trả An.
- Selection cuối cùng trả Chi.

Test:

~~~java
@Test
void selectsFirstAndLastMatchingMembers() {
    Member first = parser
        .parseExpression("members.^[active]")
        .getValue(input, Member.class);

    Member last = parser
        .parseExpression("members.$[active]")
        .getValue(input, Member.class);

    assertThat(first.getName()).isEqualTo("An");
    assertThat(last.getName()).isEqualTo("Chi");
}
~~~

Cần kiểm tra thêm trường hợp không có phần tử phù hợp. Selection đầu tiên/cuối cùng có thể trả null khi không tìm thấy phần tử; code tiêu thụ kết quả phải xử lý trường hợp đó.

Không nhầm selection đầu/cuối với việc sắp xếp collection. Chúng dựa trên thứ tự duyệt của collection nguồn.

## 7. Kiểm thử projection trên List

Projection áp dụng expression cho từng phần tử:

~~~text
members.![name]
~~~

Test:

~~~java
@Test
void projectsMemberNamesInSourceOrder() {
    List<?> names = parser
        .parseExpression("members.![name]")
        .getValue(input, List.class);

    assertThat(names)
        .containsExactly("An", "Binh", "Chi");
}
~~~

Nên kiểm tra:

- Số kết quả bằng số phần tử nguồn.
- Mỗi kết quả tương ứng với đúng phần tử.
- Thứ tự được giữ theo collection nguồn.
- Kiểu từng value đúng với expression.
- Projection không tự loại phần tử chỉ vì value trả về null.

Ví dụ projection trên property có thể null:

~~~text
members.![address?.city]
~~~

Với member Chi có address null, kết quả tại vị trí tương ứng là null. Projection vẫn tạo phần tử kết quả cho member đó.

Nếu muốn loại bỏ kết quả null, hãy kết hợp selection có điều kiện rõ ràng rồi projection:

~~~text
members.?[address != null].![address.city]
~~~

Test phải phản ánh đúng yêu cầu nghiệp vụ: giữ null ở vị trí tương ứng hay lọc bỏ phần tử nguồn trước khi projection.

## 8. Kiểm thử selection kết hợp projection

Một biểu thức có thể lọc trước rồi biến đổi:

~~~text
members.?[active].![name]
~~~

Selection giữ member active; projection lấy name của những member còn lại.

Test:

~~~java
@Test
void selectsThenProjectsNames() {
    List<?> names = parser
        .parseExpression("members.?[active].![name]")
        .getValue(input, List.class);

    assertThat(names)
        .containsExactly("An", "Chi");
}
~~~

Hãy xác nhận thứ tự thao tác. Nếu projection chạy trước, expression có thể không còn object hoặc property cần thiết cho predicate sau đó.

Với property lồng nhau, có thể lọc các member có address rồi lấy city:

~~~text
members.?[address != null].![address.city]
~~~

Test riêng cho member có address null để xác nhận selection loại đúng phần tử trước khi projection truy cập city.

## 9. Kiểm thử selection và projection trên Map

Với Map, selection predicate chạy trên Map.Entry. Có thể truy cập key và value:

~~~text
#scores.?[value >= 70]
~~~

Selection giữ entry phù hợp và trả Map.

Projection:

~~~text
#scores.![key]
~~~

trả List các key. Projection trên Map không trả Map vì mỗi entry được biến thành một giá trị.

Ví dụ test:

~~~java
@Test
void selectsMapEntriesAndProjectsKeys() {
    Map<String, Integer> scores = new LinkedHashMap<>();
    scores.put("An", 80);
    scores.put("Binh", 60);
    scores.put("Chi", 90);

    StandardEvaluationContext context =
        new StandardEvaluationContext();
    context.setVariable("scores", scores);

    Map<?, ?> selected = parser
        .parseExpression("#scores.?[value >= 70]")
        .getValue(context, Map.class);

    List<?> keys = parser
        .parseExpression("#scores.?[value >= 70].![key]")
        .getValue(context, List.class);

    assertThat(selected).containsKeys("An", "Chi");
    assertThat(keys).containsExactly("An", "Chi");
}
~~~

Dùng LinkedHashMap khi thứ tự là một phần của expected result. HashMap không bảo đảm thứ tự duyệt ổn định, vì vậy không nên viết test yêu cầu một thứ tự cụ thể trên HashMap.

## 10. Null-safe navigation trên property

Dấu ?. bảo vệ thao tác truy cập property hoặc gọi method khi receiver có thể null.

Ví dụ:

~~~text
member.address?.city
~~~

Nếu address null, biểu thức trả null thay vì cố đọc city trên null. Tuy nhiên, member vẫn phải tồn tại; nếu member cũng có thể null, cần bảo vệ cả tầng đó:

~~~text
#this?.address?.city
~~~

Test nên có các fixture:

- Member khác null, address khác null, city có giá trị.
- Member khác null, address null.
- Member null.
- Address khác null nhưng city null.

Null-safe navigation chỉ bảo vệ receiver ngay trước dấu ?. Không giả định một dấu ?. ở đầu đường dẫn sẽ bảo vệ mọi object trung gian phía sau.

## 11. Null-safe selection và projection từ Spring Framework 6.2

Spring Framework 6.2 bổ sung null-safe collection selection và projection. Cú pháp dùng ?. ngay trước toán tử collection:

~~~text
members?.?[active]
~~~

~~~text
members?.![name]
~~~

Nếu collection receiver null, null-safe operation trả null thay vì ném lỗi do thao tác selection/projection trên null.

Điều này khác với collection rỗng:

- Collection null: kết quả null khi dùng null-safe collection operator.
- Collection rỗng: selection/projection chạy trên collection rỗng và trả collection kết quả rỗng.
- Collection có phần tử: operation chạy theo từng phần tử.

Test nên xác nhận ba trạng thái riêng biệt. Không mặc định null-safe selection biến null thành empty list.

### 11.1. Bảo vệ phần tử và property lồng nhau

Null-safe collection operator chỉ bảo vệ collection receiver. Nó không tự bảo vệ từng phần tử null hoặc property trung gian null.

Ví dụ:

~~~text
members?.![#this?.address?.city]
~~~

Ở đây:

- members?. bảo vệ collection nguồn.
- #this?. bảo vệ phần tử hiện tại nếu phần tử null.
- address?. bảo vệ property address nếu null.
- city được đọc khi address tồn tại.

Tương tự, selection có thể viết:

~~~text
members?.?[#this?.active == true]
~~~

Nếu member null, biểu thức predicate trả null ở vế so sánh và không chọn phần tử đó.

## 12. Phân biệt collection null, rỗng và có phần tử null

Đây là ba fixture khác nhau và cần test riêng.

| Fixture | Ý nghĩa | Kết quả mong đợi |
|---|---|---|
| members = null | Không có collection | Null-safe selection/projection trả null |
| members = empty list | Có collection nhưng không có phần tử | Selection/projection trả List rỗng |
| members chứa null | Collection có một phần tử null | Predicate/projection cần bảo vệ phần tử nếu truy cập property |

Ví dụ tạo collection có phần tử null:

~~~java
List<Member> membersWithNull =
    Arrays.asList(an, null, chi);
~~~

Selection không bảo vệ phần tử:

~~~text
members.?[active]
~~~

có thể thất bại khi predicate truy cập active trên phần tử null.

Selection bảo vệ phần tử:

~~~text
members.?[#this?.active == true]
~~~

Projection bảo vệ phần tử và property lồng nhau:

~~~text
members.![#this?.address?.city]
~~~

Test các trường hợp này giúp phân biệt rõ null-safe receiver với null-safe element.

## 13. Phiên bản Spring trước 6.2

Nếu ứng dụng dùng phiên bản Spring chưa hỗ trợ null-safe selection/projection trên collection, không dùng cú pháp ?. trước các toán tử này.

Có thể guard collection bằng toán tử điều kiện:

~~~text
members == null ? null : members.![name]
~~~

Hoặc trả collection rỗng nếu đó là hợp đồng mong muốn:

~~~text
members == null ? {} : members.![name]
~~~

Với lựa chọn này, test phải xác nhận chính sách null rõ ràng: trả null hay trả empty collection. Hai kết quả mang ý nghĩa khác nhau.

Property null-safe navigation bằng ?. đã có trước null-safe collection operation; không đánh đồng phiên bản hỗ trợ ?.property với phiên bản hỗ trợ ?.![...] hoặc ?.?[...]. Kiểm tra phiên bản Spring thực tế trước khi dùng cú pháp mới.

## 14. Kiểm tra kiểu và hình dạng kết quả

Test selection/projection nên xác nhận cả kiểu collection:

| Nguồn | Operation | Hình dạng kết quả |
|---|---|---|
| List | Selection | List các object nguồn phù hợp |
| List | Projection | List các giá trị được tính |
| Map | Selection | Map các entry phù hợp |
| Map | Projection | List các giá trị được tính từ entry |
| Null collection với null-safe operation | Selection/projection | Null |
| Empty List | Selection/projection | List rỗng |

Không ép kết quả Map selection thành List hoặc ngược lại. Nếu API Java yêu cầu kiểu cụ thể, dùng getValue(context, ExpectedType.class) và assert kiểu đó trong test.

Với projection trả nhiều loại giá trị hoặc map lồng nhau, kiểm tra từng phần tử và key quan trọng. Đừng chỉ kiểm tra toString() của collection vì định dạng chuỗi có thể che giấu kiểu và cấu trúc thực tế.

## 15. Ví dụ JUnit cho null-safe navigation

Ví dụ dưới đây dùng root object có property members để có thể biểu diễn collection null:

~~~java
@Test
void nullSafeProjectionReturnsNullForNullCollection() {
    MemberInput nullInput = new MemberInput(null);

    Object result = parser
        .parseExpression("members?.![name]")
        .getValue(nullInput);

    assertThat(result).isNull();
}
~~~

Test collection rỗng:

~~~java
@Test
void projectionReturnsEmptyListForEmptyCollection() {
    MemberInput emptyInput =
        new MemberInput(Collections.emptyList());

    List<?> result = parser
        .parseExpression("members?.![name]")
        .getValue(emptyInput, List.class);

    assertThat(result).isEmpty();
}
~~~

Test phần tử null và property lồng nhau:

~~~java
@Test
void projectionHandlesNullElementsAndNestedProperties() {
    List<Member> values =
        Arrays.asList(an, null, chi);

    MemberInput input = new MemberInput(values);

    List<?> cities = parser
        .parseExpression(
            "members?.![#this?.address?.city]")
        .getValue(input, List.class);

    assertThat(cities).containsExactly("Hanoi", null, null);
}
~~~

Các test này chỉ dùng null-safe collection operator khi ứng dụng chạy Spring Framework 6.2 trở lên. Với phiên bản cũ hơn, dùng guard expression phù hợp hoặc xử lý null collection trong Java trước khi evaluate.

## 16. Kiểm thử lỗi và hành vi không mong muốn

Không phải mọi lỗi liên quan selection/projection đều là lỗi cú pháp. Một expression có thể parse thành công nhưng thất bại khi evaluate.

Các trường hợp cần kiểm tra:

- Collection source null nhưng dùng operation không null-safe.
- Phần tử null và predicate truy cập property trực tiếp.
- Property trung gian null mà không có safe navigation.
- Property không tồn tại hoặc getter không truy cập được.
- Predicate gọi method không được phép hoặc method ném exception.
- Kiểu phần tử không đồng nhất.
- Map value null nhưng predicate so sánh như số.
- Projection tạo kết quả không đúng kiểu mà code Java mong đợi.

Test nên phân biệt lỗi parse, lỗi evaluate và kết quả nghiệp vụ rỗng. Không bắt mọi exception rồi trả collection rỗng vì điều đó có thể che giấu lỗi model hoặc lỗi cấu hình.

## 17. Tổ chức bộ test bằng parameterized test

Có thể dùng JUnit parameterized test để chạy nhiều fixture qua cùng một expression.

Ví dụ các trường hợp:

- Danh sách có cả active và inactive.
- Danh sách rỗng.
- Collection null.
- Danh sách chứa phần tử null.
- Property lồng nhau null.
- Tất cả phần tử đều không thỏa predicate.

Mỗi test case nên khai báo:

1. Input fixture.
2. Expression source.
3. Kiểu kết quả mong đợi.
4. Giá trị hoặc exception mong đợi.
5. Phiên bản/capability cần có nếu dùng cú pháp mới.

Parameterized test giúp đảm bảo các trường hợp biên được chạy lặp lại mỗi khi model hoặc expression thay đổi. Tuy nhiên, giữ tên test và dữ liệu đủ rõ để khi thất bại có thể xác định fixture nào gây lỗi.

## 18. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Selection lỗi khi collection null | Dùng .?[] trên receiver null | Dùng null-safe selection trên Spring 6.2+ hoặc guard trước |
| Projection lỗi khi collection null | Dùng .![] trên receiver null | Dùng null-safe projection hoặc guard |
| Null-safe collection vẫn lỗi với phần tử null | Chỉ bảo vệ collection receiver | Dùng #this?.property trong predicate/projection |
| Property lồng nhau vẫn lỗi | Một tầng trung gian null chưa được bảo vệ | Đặt ?. ở từng receiver có thể null |
| Test mong empty list nhưng nhận null | Null-safe operation giữ ngữ nghĩa null | Quy định rõ null hay empty và dùng default nếu cần |
| Selection trả object thay vì value | Selection giữ phần tử nguồn | Dùng projection nếu cần biến đổi |
| Projection trả List thay vì Map | Projection tạo kết quả theo từng entry | Dùng selection nếu cần giữ key-value |
| Test thứ tự không ổn định | Dùng HashMap hoặc collection không bảo đảm thứ tự | Dùng List/LinkedHashMap khi thứ tự là hợp đồng |
| Expression parse được nhưng evaluate lỗi | Dữ liệu, property hoặc method không phù hợp | Kiểm tra context và fixture |
| Cú pháp null-safe collection không được hỗ trợ | Spring version cũ hơn 6.2 | Dùng conditional guard tương thích |

## 19. Bài tập thực hành

1. Tạo List Member có active true/false và test selection .?[active].
2. Test selection đầu tiên và cuối cùng bằng .^[...] và .$[...].
3. Test projection .![name] và xác nhận thứ tự.
4. Kết hợp selection rồi projection để lấy tên member active.
5. Tạo Map<String, Integer>, selection theo value và projection lấy key.
6. Tạo collection rỗng và xác nhận kết quả selection/projection.
7. Tạo root DTO có collection null và test null-safe selection/projection.
8. Tạo List chứa phần tử null; so sánh predicate trực tiếp với predicate dùng #this?.
9. Tạo object có address null và test property path address?.city.
10. Test nested projection với collection con null và phần tử con null.
11. Viết parameterized test cho các trạng thái null, empty, populated và mixed.
12. Chạy test trên đúng phiên bản Spring mà ứng dụng triển khai.

## 20. Checklist trước khi dùng selection, projection và null-safe navigation

- [ ] Selection có lọc đúng phần tử theo predicate không?
- [ ] Projection có tạo đúng giá trị cho từng phần tử không?
- [ ] Đã phân biệt kết quả List và Map chưa?
- [ ] Thứ tự kết quả có phù hợp với collection nguồn không?
- [ ] Đã test selection đầu tiên/cuối cùng nếu sử dụng chưa?
- [ ] Đã test collection null và collection rỗng riêng biệt chưa?
- [ ] Đã test collection có phần tử null chưa?
- [ ] Mỗi property trung gian có thể null đã được bảo vệ chưa?
- [ ] Đã phân biệt null-safe collection với null-safe element chưa?
- [ ] Có dùng cú pháp null-safe collection phù hợp với Spring 6.2+ không?
- [ ] Với Spring cũ, đã có conditional guard tương thích chưa?
- [ ] Test có kiểm tra kiểu kết quả, giá trị và exception không?
- [ ] Có tránh bắt mọi exception rồi âm thầm trả collection rỗng không?

## 21. Kết luận

Selection .?[] lọc phần tử, .^[] và .$[] lấy phần tử phù hợp đầu tiên/cuối cùng, còn projection .![] biến đổi từng phần tử thành collection kết quả. Null-safe property navigation bảo vệ receiver tại từng dấu ?., trong khi null-safe selection/projection trên collection được hỗ trợ từ Spring Framework 6.2. Hãy kiểm thử riêng collection null, collection rỗng, phần tử null và property lồng nhau null; xác nhận cả kiểu, thứ tự và hình dạng kết quả. Khi chạy trên phiên bản cũ, dùng guard tường minh thay cho cú pháp null-safe collection mới.