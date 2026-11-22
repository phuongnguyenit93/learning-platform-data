# List và map rỗng

## 1. Inline collection trong SpEL

Spring Expression Language (SpEL) cho phép khai báo trực tiếp List và Map ngay trong chuỗi biểu thức. Cách viết này gọi là inline collection vì dữ liệu được mô tả ngay tại vị trí cần dùng, không phải tạo sẵn một collection trong Java rồi truyền vào context.

Hai dạng cơ bản:

    {1, 2, 3}                         // Inline List
    {name: 'Nikola', age: 86}         // Inline Map

SpEL cũng có cú pháp riêng cho collection rỗng:

    {}                                // Empty List
    {:}                               // Empty Map

Hai biểu thức rỗng này khác nhau về kiểu dữ liệu và không thể thay thế cho nhau. Đây là điểm quan trọng nhất của bài học.

## 2. Khởi tạo List có phần tử

Inline List sử dụng cặp dấu ngoặc nhọn và các phần tử được phân tách bằng dấu phẩy:

    {1, 2, 3, 4}

Khi đánh giá, biểu thức trả về một đối tượng Java List chứa các phần tử theo thứ tự đã khai báo.

Ví dụ:

    ExpressionParser parser = new SpelExpressionParser();

    List<?> numbers = (List<?>) parser
        .parseExpression("{1, 2, 3, 4}")
        .getValue();

    // numbers = [1, 2, 3, 4]

Có thể sử dụng các literal khác nhau:

    {'Spring', 'Boot', 'Framework'}
    {true, false, true}
    {10, 20.5, 30}

Phần tử trong List có thể là các biểu thức SpEL. Vì vậy, List có thể chứa giá trị literal, variable, phép toán hoặc kết quả của lời gọi được phép trong EvaluationContext.

Ví dụ:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("minimum", 18);

    List<?> values = (List<?>) parser
        .parseExpression("{#minimum, #minimum + 1, #minimum + 2}")
        .getValue(context);

    // values = [18, 19, 20]

SpEL đánh giá từng phần tử rồi tạo kết quả List tương ứng.

## 3. List lồng nhau

Một inline List có thể chứa các inline List khác. Đây là cách biểu diễn cấu trúc dạng ma trận hoặc nhóm dữ liệu nhiều tầng.

Ví dụ:

    {{'a', 'b'}, {'x', 'y'}}

Kết quả là một List gồm hai phần tử, mỗi phần tử lại là một List:

    [
        ['a', 'b'],
        ['x', 'y']
    ]

Có thể lấy phần tử bằng indexer:

    {{'a', 'b'}, {'x', 'y'}}[0][1]

Kết quả là:

    b

Index bắt đầu từ 0. Indexer đầu tiên chọn List con ở vị trí 0; indexer tiếp theo chọn phần tử tại vị trí 1 trong List con đó.

Khi cấu trúc lồng nhau sâu, nên xuống dòng và thụt lề trong chuỗi expression để dễ đọc:

    {
        {'java', 'spring'},
        {'kotlin', 'coroutines'}
    }

Khoảng trắng giữa các token được parser bỏ qua, nên có thể định dạng biểu thức nhiều dòng mà không làm thay đổi cấu trúc dữ liệu.

## 4. Cú pháp List rỗng: {}

Trong SpEL, chỉ cần cặp ngoặc nhọn không có phần tử:

    {}

là biểu diễn một List rỗng.

Ví dụ:

    Expression emptyListExpression =
        parser.parseExpression("{}");

    List<?> emptyList =
        (List<?>) emptyListExpression.getValue();

    // emptyList = []

Đối tượng trả về là List có kích thước bằng 0. Có thể kiểm tra:

    emptyList.isEmpty();   // true
    emptyList.size();      // 0

List rỗng hữu ích khi một biểu thức cần trả về cùng một kiểu collection trong mọi nhánh xử lý, hoặc khi dữ liệu tùy chọn chưa có phần tử nào.

Không được hiểu {} là null. Null là một giá trị riêng:

    null

Hai kết quả khác nhau:

| Expression | Giá trị |
| --- | --- |
| {} | List rỗng |
| null | null |

Vì vậy, kiểm tra null và kiểm tra List rỗng là hai thao tác khác nhau.

## 5. Khởi tạo Map có phần tử

Inline Map sử dụng dấu ngoặc nhọn, trong đó mỗi entry có dạng key:value. Các entry được phân tách bằng dấu phẩy.

Ví dụ:

    {name: 'Nikola', dob: '10-July-1856'}

Kết quả là một Java Map có hai cặp key-value:

    {
        "name": "Nikola",
        "dob": "10-July-1856"
    }

Có thể đánh giá expression trong Java:

    Map<?, ?> inventorInfo = (Map<?, ?>) parser
        .parseExpression(
            "{name: 'Nikola', dob: '10-July-1856'}"
        )
        .getValue();

    // inventorInfo.get("name") = "Nikola"

Tên key không bắt buộc phải đặt trong dấu nháy nếu đó là identifier phù hợp. Tuy nhiên, có thể đặt key trong dấu nháy để thể hiện rõ đó là chuỗi:

    {'name': 'Nikola', 'dob': '10-July-1856'}

Nếu key chứa dấu chấm, cần đặt key trong dấu nháy:

    {'user.name': 'Lan'}

Ở đây key là một chuỗi duy nhất user.name, không phải đường dẫn truy cập property user rồi đến name.

Giá trị sau dấu hai chấm là biểu thức SpEL. Vì vậy, Map có thể chứa số, chuỗi, boolean, null, variable hoặc collection khác.

## 6. Cú pháp Map rỗng: {:}

SpEL dùng cú pháp riêng để biểu diễn Map rỗng:

    {:}

Kết quả là một Java Map không có entry nào.

Ví dụ:

    Expression emptyMapExpression =
        parser.parseExpression("{:}");

    Map<?, ?> emptyMap =
        (Map<?, ?>) emptyMapExpression.getValue();

    // emptyMap = {}

Có thể kiểm tra:

    emptyMap.isEmpty();    // true
    emptyMap.size();       // 0

Điểm dễ nhầm là List rỗng và Map rỗng đều không có phần tử, nhưng cú pháp của chúng khác nhau:

| Kiểu dữ liệu | Inline syntax | Kiểu kết quả |
| --- | --- | --- |
| List rỗng | {} | List |
| Map rỗng | {:} | Map |
| Giá trị null | null | null |

Không dùng {} khi cần Map rỗng. Parser hiểu {} là List rỗng. Tương tự, không dùng {:} để biểu diễn List.

## 7. Map lồng nhau

Map có thể chứa Map khác làm value. Cách này phù hợp với dữ liệu có cấu trúc phân cấp, ví dụ thông tin cá nhân, ngày sinh hoặc địa chỉ.

Ví dụ:

    {
        name: {
            first: 'Nikola',
            last: 'Tesla'
        },
        dob: {
            day: 10,
            month: 'July',
            year: 1856
        }
    }

Kết quả là một Map có hai key cấp ngoài: name và dob. Mỗi key trỏ đến một Map con.

Có thể truy cập giá trị lồng nhau bằng key:

    {
        name: {first: 'Nikola', last: 'Tesla'},
        dob: {day: 10, month: 'July', year: 1856}
    }['name']['first']

Kết quả là:

    Nikola

Map lồng nhau giúp biểu diễn dữ liệu dạng object mà không cần định nghĩa class Java riêng cho từng cấu trúc trung gian. Tuy nhiên, nếu dữ liệu là model nghiệp vụ có quy tắc và kiểu rõ ràng, một class hoặc record Java thường dễ bảo trì hơn một Map nhiều tầng.

## 8. List và Map có thể kết hợp với nhau

Inline List có thể chứa Map, và inline Map có thể chứa List. Có thể kết hợp hai cấu trúc để biểu diễn dữ liệu gần với JSON.

Ví dụ List các Map:

    {
        {id: 1, name: 'Lan'},
        {id: 2, name: 'Minh'}
    }

Đây là một List có hai phần tử Map.

Ví dụ Map chứa List:

    {
        team: 'Platform',
        members: {'Lan', 'Minh', 'An'}
    }

Ví dụ Map lồng nhau có List:

    {
        department: {
            name: 'Engineering',
            skills: {'Java', 'Spring', 'SQL'}
        }
    }

Có thể truy cập dữ liệu qua nhiều cấp:

    {
        department: {
            name: 'Engineering',
            skills: {'Java', 'Spring', 'SQL'}
        }
    }['department']['skills'][1]

Kết quả là:

    Spring

Khi kết hợp nhiều tầng, hãy xác định rõ từng cấp là List hay Map. Dùng index số cho List và key cho Map.

## 9. Dùng variable và biểu thức động trong collection

Inline collection không chỉ chứa literal cố định. Các phần tử và value có thể tham chiếu variable từ EvaluationContext.

Ví dụ:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("name", "Lan");
    context.setVariable("score", 92);

    List<?> summary = (List<?>) parser
        .parseExpression("{#name, #score, #score >= 80}")
        .getValue(context);

    // summary = ["Lan", 92, true]

Ví dụ Map:

    Map<?, ?> profile = (Map<?, ?>) parser
        .parseExpression(
            "{name: #name, score: #score, passed: #score >= 80}"
        )
        .getValue(context);

    // profile.get("passed") = true

Điều này cho phép biểu thức tạo collection từ dữ liệu runtime. Parser tạo cấu trúc expression; khi getValue được gọi, các variable và phép toán được đánh giá trong context được cung cấp.

Nếu variable chưa được đăng ký, expression có thể parse thành công nhưng evaluation thất bại khi cần đọc variable đó.

## 10. Phân biệt inline List/Map với array construction

Dấu ngoặc nhọn cũng xuất hiện trong cú pháp khởi tạo array, nhưng hai cách viết có kiểu kết quả khác nhau.

Inline List:

    {1, 2, 3}

Array construction:

    new int[]{1, 2, 3}

Ví dụ:

    List<?> numbers = (List<?>) parser
        .parseExpression("{1, 2, 3}")
        .getValue();

    int[] numberArray = (int[]) parser
        .parseExpression("new int[]{1, 2, 3}")
        .getValue();

Kết quả đầu tiên là List. Kết quả thứ hai là int array.

Tương tự, inline Map là Map; nó không phải object Java tùy ý hoặc array. Hãy chọn cú pháp dựa trên kiểu dữ liệu mà code phía sau cần nhận.

## 11. Constant collection và hiệu năng

SpEL có tối ưu cho inline collection chỉ chứa các giá trị cố định.

- Nếu List chỉ gồm literal cố định, SpEL tạo một constant List để biểu diễn expression thay vì xây dựng List mới ở mỗi lần evaluation.
- Nếu Map chỉ gồm literal cố định hoặc các cấu trúc List/Map lồng nhau cũng là constant, SpEL có thể tạo constant Map tương tự.
- Nếu phần tử hoặc value phụ thuộc variable hay biểu thức runtime, collection cần được đánh giá theo dữ liệu của context.

Ví dụ constant:

    {1, 2, 3}
    {name: 'Lan', active: true}
    {name: {first: 'Nikola', last: 'Tesla'}}

Ví dụ có dữ liệu runtime:

    {#minimum, #minimum + 1}
    {name: #customerName}

Tối ưu constant có nghĩa SpEL không cần xây dựng lại cấu trúc chỉ chứa literal ở mỗi lần gọi. Vì vậy, không nên giả định mỗi lần getValue sẽ trả về một collection độc lập để có thể sửa đổi mà không ảnh hưởng lần đánh giá khác.

Nếu nghiệp vụ cần một List hoặc Map mutable riêng cho mỗi request, hãy tạo bản sao trong Java trước khi thêm, xóa hoặc thay đổi entry:

    List<Object> mutableCopy =
        new ArrayList<>(constantList);

    Map<Object, Object> mutableMapCopy =
        new HashMap<>(constantMap);

Cách này giúp vòng đời dữ liệu mutable được quản lý rõ ràng ở Java.

## 12. Sử dụng collection rỗng trong logic ứng dụng

List rỗng và Map rỗng thường được dùng làm giá trị mặc định cho dữ liệu tùy chọn.

Ví dụ chọn List rỗng khi variable chưa có giá trị:

    #members ?: {}

Nếu members là null, Elvis chọn List rỗng. Nếu members đã là List có dữ liệu, giá trị đó được giữ nguyên.

Tương tự, Map rỗng:

    #settings ?: {:}

Nếu settings là null, kết quả là Map rỗng.

Cần chú ý kiểu của giá trị mặc định phải phù hợp với kiểu mà logic phía sau mong đợi:

- Collection các phần tử: dùng {}
- Map key-value: dùng {:}

Không thay Map rỗng bằng List rỗng chỉ vì cả hai đều không có phần tử. Code truy cập key của Map và code truy cập index của List có hành vi khác nhau.

Nếu cần phân biệt null với collection rỗng, đừng dùng Elvis để thay null. Hãy kiểm tra trực tiếp:

    #members == null
    #members != null and #members.isEmpty()

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Cần Map nhưng nhận List | Dùng {} thay vì {:} | Dùng đúng cú pháp Map rỗng |
| Parse error khi tạo Map rỗng | Thiếu dấu hai chấm trong {:} | Viết chính xác {:} |
| Không truy cập được Map key | Key không đúng hoặc sai kiểu | Kiểm tra key và dùng dấu nháy khi cần |
| Indexer không phù hợp | Dùng index số cho Map hoặc key cho List | Phân biệt List index và Map key |
| Variable không tìm thấy | Chưa gọi setVariable hoặc sai tên | Kiểm tra EvaluationContext |
| Dữ liệu không đổi giữa các lần đánh giá | Inline collection chỉ gồm literal có thể được tối ưu thành constant | Tạo bản sao mutable nếu cần cập nhật |
| Nhầm collection rỗng với null | Dùng cú pháp {} hoặc {:} nhưng kỳ vọng null | Dùng literal null khi cần biểu diễn null |

Khi debug, hãy kiểm tra expression trả về kiểu nào trước khi truy cập dữ liệu:

    Object listValue = parser.parseExpression("{}").getValue();
    Object mapValue = parser.parseExpression("{:}").getValue();

Sau đó kiểm tra kiểu thực tế bằng Java:

    listValue instanceof List
    mapValue instanceof Map

Điều này giúp xác định parser đang tạo đúng loại collection hay không.

## 14. Những điểm cần nhớ

- Inline List dùng {value1, value2, ...}.
- List rỗng dùng {}.
- Inline Map dùng {key: value, ...}.
- Map rỗng dùng {:}.
- {} và {:} có kiểu kết quả khác nhau.
- List và Map có thể lồng nhau hoặc chứa collection của kiểu còn lại.
- Value có thể là literal, variable hoặc biểu thức runtime.
- Key của Map có thể không cần dấu nháy nếu là identifier phù hợp; key chứa dấu chấm cần được đặt trong dấu nháy.
- Collection chỉ chứa literal cố định có thể được tối ưu thành constant và tái sử dụng khi evaluation.
- Không giả định constant collection là bản mutable mới ở mỗi lần getValue.
- Inline List/Map khác với array construction như new int[]{1, 2, 3}.
- Collection rỗng khác null; hãy chọn đúng kiểu dữ liệu cho logic phía sau.

Khi viết inline collection trong SpEL, hãy xác định trước cấu trúc cần tạo là List hay Map. Đặc biệt, nhớ hai cú pháp rỗng {} và {:} để tránh lỗi kiểu dữ liệu ở các bước xử lý tiếp theo.

## Tài liệu tham khảo

- Spring Framework Reference — Inline Lists: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/inline-lists.html
- Spring Framework Reference — Inline Maps: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/inline-maps.html
- Spring Framework Reference — Properties, Arrays, Lists, Maps, and Indexers: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/properties-arrays.html
