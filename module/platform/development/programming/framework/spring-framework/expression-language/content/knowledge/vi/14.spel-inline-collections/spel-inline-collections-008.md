# Truy cập phần tử sau khi tạo collection trong SpEL

Spring Expression Language (SpEL) hỗ trợ tạo list, map và array ngay trong biểu thức. Sau khi tạo collection, có thể dùng toán tử index `[]` để lấy một phần tử theo vị trí hoặc theo khóa. Có thể truy cập trực tiếp trên collection literal, trên biến/property đã có trong EvaluationContext hoặc trên kết quả của một expression khác.

Cần phân biệt chỉ số của list/array với khóa của map: list và array dùng chỉ số bắt đầu từ 0, còn map dùng key để tìm value. Khi truy cập collection lồng nhau, mỗi cặp ngoặc vuông chọn một cấp dữ liệu.

## 1. Toán tử index cơ bản

Cú pháp tổng quát:

    target[index]

Trong đó `target` là list, array, map hoặc kiểu dữ liệu được SpEL hỗ trợ truy cập theo index; `index` là vị trí hoặc khóa cần lấy.

Ví dụ với list:

    {'red', 'green', 'blue'}[0]   // 'red'
    {'red', 'green', 'blue'}[1]   // 'green'
    {'red', 'green', 'blue'}[2]   // 'blue'

Chỉ số của list bắt đầu từ 0. Vì vậy phần tử đầu tiên ở vị trí 0, phần tử thứ hai ở vị trí 1. Chỉ số bằng độ dài list hoặc lớn hơn sẽ vượt phạm vi hợp lệ.

Có thể lưu list vào biến rồi truy cập:

    #colors[1]

Trong trường hợp này, `colors` phải được đăng ký trong EvaluationContext và chứa một List hoặc collection có thể truy cập theo index.

## 2. Truy cập ngay sau khi tạo inline list

SpEL cho phép đặt toán tử index ngay sau inline list literal:

    {'Spring', 'Framework', 'SpEL'}[2]

Biểu thức trên trả về phần tử thứ ba, tức `'SpEL'`. Không cần tạo biến trung gian nếu chỉ cần một giá trị tại vị trí cụ thể.

Ví dụ lấy một phần tử từ danh sách mã trạng thái:

    {'NEW', 'PROCESSING', 'DONE'}[1]

Kết quả là `'PROCESSING'`. Đây là cách viết ngắn gọn cho dữ liệu cố định, nhỏ và được dùng ngay tại vị trí biểu thức.

Với list rỗng `{}`, không có chỉ số hợp lệ. Trước khi truy cập phần tử, cần bảo đảm collection có ít nhất một phần tử.

## 3. Truy cập phần tử của array

Array cũng dùng toán tử index và chỉ số bắt đầu từ 0. Có thể tạo array bằng cú pháp tạo mảng của SpEL:

    new int[]{10, 20, 30}[0]
    new int[]{10, 20, 30}[2]

Biểu thức thứ nhất lấy giá trị 10, biểu thức thứ hai lấy giá trị 30.

Có thể lưu array trong biến Java rồi đưa vào context:

    int[] levels = {1, 3, 5, 7};

    StandardEvaluationContext context =
            new StandardEvaluationContext();
    context.setVariable("levels", levels);

    ExpressionParser parser = new SpelExpressionParser();
    Object selected = parser.parseExpression("#levels[2]")
            .getValue(context);

Kết quả là phần tử có chỉ số 2, tức 5. Với array đa chiều, dùng nhiều cặp ngoặc vuông:

    new int[][]{{1, 2}, {3, 4}}[1][0]

Biểu thức trên lấy hàng thứ hai rồi lấy phần tử đầu tiên của hàng đó, kết quả là 3.

## 4. Truy cập value trong inline map

Map không dùng vị trí số để truy cập phần tử; nó dùng key. Inline map của SpEL được viết bằng các cặp key-value trong dấu ngoặc nhọn:

    {'name': 'An', 'role': 'EDITOR', 'active': true}

Dùng toán tử index với key để lấy value:

    {'name': 'An', 'role': 'EDITOR'}['name']

Kết quả là `'An'`.

Ví dụ lấy một giá trị khác:

    {'code': 'EXPRESS', 'fee': 25000}['fee']

Kết quả là 25000. Dùng cú pháp `map['key']` giúp thể hiện rõ rằng đang truy cập theo khóa. Cách này cũng thuận tiện khi key có ký tự đặc biệt hoặc được lưu trong biến.

Map rỗng có thể được biểu diễn bằng `{:}`. Map không chứa key được yêu cầu thường trả về null cho lần truy cập đó; hãy phân biệt trường hợp key không tồn tại với trường hợp key có tồn tại nhưng value của nó vốn là null nếu nghiệp vụ cần phân biệt hai tình huống này.

## 5. Dùng biến làm index hoặc key

Index không nhất thiết phải là literal. Có thể dùng biến được đăng ký trong EvaluationContext:

    context.setVariable("colors", List.of("red", "green", "blue"));
    context.setVariable("position", 2);

    Object color = parser.parseExpression("#colors[#position]")
            .getValue(context);

Biểu thức lấy phần tử ở vị trí được cung cấp bởi biến `position`. Cách này hữu ích khi vị trí đến từ lựa chọn của người dùng hoặc một phép tính ở Java.

Tương tự, key của map có thể là biến:

    context.setVariable("settings",
            Map.of("language", "vi", "theme", "dark"));
    context.setVariable("settingName", "theme");

    Object theme = parser.parseExpression(
            "#settings[#settingName]"
    ).getValue(context);

Kết quả là `'dark'`. Khi key động, cần kiểm tra key có thuộc tập được phép truy cập hay không nếu map chứa dữ liệu nhạy cảm hoặc có phạm vi lớn.

Index cũng có thể là một expression:

    #values[#start + 1]

SpEL đánh giá biểu thức chỉ số trước rồi dùng kết quả để truy cập phần tử. Với list hoặc array, chỉ số cuối cùng phải là một giá trị số nguyên hợp lệ.

## 6. Truy cập collection lồng nhau

Một collection có thể chứa collection khác. Khi đó, mỗi lần dùng `[]` là đi sâu thêm một cấp:

    {{'A', 'B'}, {'C', 'D'}}[1][0]

Bước đầu lấy list con ở vị trí 1, tức `{'C', 'D'}`; bước tiếp theo lấy phần tử ở vị trí 0, kết quả là `'C'`.

Map cũng có thể chứa list:

    {'scores': {8, 9, 10}}['scores'][1]

Biểu thức lấy list ở key `scores`, sau đó lấy phần tử thứ hai, kết quả là 9.

Một list có thể chứa các map:

    {
        {'id': 101, 'name': 'Lan'},
        {'id': 102, 'name': 'Minh'}
    }[1]['name']

Biểu thức lấy map thứ hai trong list, rồi đọc value tại key `name`, kết quả là `'Minh'`.

Với dữ liệu lồng nhau, hãy kiểm tra từng cấp một. Nếu list con hoặc map con là null, thao tác index ở cấp tiếp theo có thể thất bại.

## 7. Kết hợp index với property và method

Sau khi lấy phần tử, có thể tiếp tục đọc property hoặc gọi method trên phần tử đó:

    #orders[0].status
    #customers[1].getDisplayName()
    #products[0].price

Các biểu thức trên lần lượt lấy phần tử đầu tiên rồi đọc property, gọi method hoặc lấy giá trị property của sản phẩm.

Có thể truy cập phần tử từ kết quả method:

    #orderService.findRecentOrders()[0]

Method `findRecentOrders()` được gọi trước; sau đó toán tử index lấy phần tử đầu tiên trong kết quả. Điều này đòi hỏi method trả về một collection hoặc array có phần tử.

Nếu method trả về null hoặc collection rỗng, index tiếp theo không thể lấy phần tử. Với method có tác dụng phụ, hãy cân nhắc việc đánh giá biểu thức nhiều lần; lời gọi method trong đường dẫn index vẫn được thực thi mỗi lần Expression được đánh giá.

## 8. Kiểm tra null và phạm vi chỉ số

Trước khi truy cập phần tử theo vị trí, cần xác định collection có null hoặc rỗng không. Có thể dùng điều kiện:

    #items != null and #items.size() > 0
        ? #items[0]
        : null

Toán tử AND trong SpEL có short-circuit. Nếu `#items != null` là false, phần kiểm tra size không được đánh giá. Nếu collection tồn tại nhưng rỗng, biểu thức trả về null thay vì truy cập index 0.

Với vị trí động:

    #items != null and
    #position >= 0 and
    #position < #items.size()
        ? #items[#position]
        : null

Điều kiện này kiểm tra collection, chỉ số không âm và chỉ số nhỏ hơn kích thước trước khi truy cập. Nếu index lấy từ dữ liệu bên ngoài, nên xác thực kiểu và giới hạn ngay ở tầng Java trước khi đưa vào context.

Đối với array, dùng thuộc tính `length` để kiểm tra số phần tử:

    #numbers != null and
    #position >= 0 and
    #position < #numbers.length
        ? #numbers[#position]
        : null

Không dùng `size()` cho array; `size()` thường được dùng với collection, còn array có thuộc tính `length`.

## 9. Phân biệt index với selection và projection

Toán tử index `[]` lấy một phần tử theo vị trí hoặc key. Nó không lọc hay biến đổi toàn bộ collection.

SpEL có các toán tử collection riêng:

- Selection `.?[condition]` lọc các phần tử thỏa điều kiện.
- Projection `.![expression]` tạo collection mới từ kết quả của expression áp dụng lên từng phần tử.
- Selection lấy phần tử đầu tiên phù hợp có thể dùng `.^[condition]`; phần tử cuối cùng phù hợp dùng `.$[condition]`.

Ví dụ, lấy phần tử đầu tiên theo vị trí:

    #orders[0]

Lọc các đơn hàng đã thanh toán:

    #orders.?[status == 'PAID']

Lấy danh sách mã đơn hàng:

    #orders.![id]

Có thể kết hợp kết quả selection với index khi cần, nhưng hãy cân nhắc collection rỗng và null trước khi lấy phần tử. Dùng đúng toán tử giúp biểu thức thể hiện rõ mục đích: index để chọn theo vị trí/key, selection để lọc, projection để chuyển đổi từng phần tử.

## 10. Ví dụ đầy đủ trong Java

Ví dụ sau tạo list và map trong Java, đưa chúng vào EvaluationContext rồi truy cập các phần tử bằng SpEL:

    List<String> names = List.of("Lan", "Minh", "An");

    Map<String, Object> profile = Map.of(
            "name", "Lan",
            "scores", List.of(8, 9, 10)
    );

    StandardEvaluationContext context =
            new StandardEvaluationContext();
    context.setVariable("names", names);
    context.setVariable("profile", profile);

    ExpressionParser parser = new SpelExpressionParser();

    String secondName = parser.parseExpression("#names[1]")
            .getValue(context, String.class);

    Integer middleScore = parser.parseExpression(
            "#profile['scores'][1]"
    ).getValue(context, Integer.class);

Kết quả `secondName` là `"Minh"`, còn `middleScore` là 9. Ví dụ này minh họa việc truy cập list theo chỉ số, map theo key và tiếp tục index một collection được lấy từ map.

Có thể parse Expression một lần rồi tái sử dụng với các context khác nhau nếu biểu thức không phụ thuộc vào trạng thái parse-time. Việc đánh giá vẫn dùng dữ liệu hiện tại trong context được truyền vào.

## 11. Lỗi thường gặp

- **Dùng chỉ số ngoài phạm vi:** list hoặc array không có phần tử ở vị trí đó sẽ gây lỗi đánh giá. Kiểm tra kích thước trước khi truy cập.
- **Dùng index số cho map:** map cần key, ví dụ `#map['code']`, không phải vị trí phần tử.
- **Nhầm key với property:** `'name'` là literal chuỗi; `name` là property được tra cứu theo target hiện tại.
- **Quên dấu `#` trước biến:** biến trong EvaluationContext phải được tham chiếu bằng `#variable`.
- **Truy cập collection null:** kiểm tra collection trước khi gọi `size()` hoặc index.
- **Index lồng nhau trên phần tử null:** kiểm tra từng cấp collection/map trước khi tiếp tục.
- **Nhầm index với selection:** dùng `[]` để lấy phần tử theo vị trí/key; dùng `.?[...]` để lọc.
- **Giả định mọi Collection đều có cùng thứ tự:** index có ý nghĩa vị trí; với cấu trúc không bảo đảm thứ tự, hãy chọn một collection có thứ tự hoặc chuyển đổi dữ liệu trước.

## 12. Ghi nhớ

Sau khi tạo inline list, map hoặc array trong SpEL, dùng `[]` để truy cập phần tử ngay trong cùng biểu thức. List và array dùng chỉ số bắt đầu từ 0; map dùng key. Index có thể là literal, biến hoặc expression, và có thể nối nhiều lần để truy cập collection lồng nhau. Có thể tiếp tục đọc property hoặc gọi method trên phần tử vừa lấy. Trước khi index dữ liệu động, hãy kiểm tra null và giới hạn vị trí; dùng selection hoặc projection khi mục tiêu là lọc hoặc biến đổi collection thay vì lấy một phần tử cụ thể.
