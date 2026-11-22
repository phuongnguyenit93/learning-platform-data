# First selection .^[] và last selection .$[] trong SpEL

Spring Expression Language (SpEL) cung cấp các toán tử selection để tìm phần tử trong list, array hoặc map theo một điều kiện Boolean. Selection thông thường `.?[condition]` trả về tất cả phần tử phù hợp. Khi chỉ cần kết quả đầu tiên hoặc cuối cùng, có thể dùng **first selection** `.^[condition]` và **last selection** `.$[condition]`.

Hai toán tử này giúp biểu thức ngắn gọn khi cần tìm một phần tử theo tiêu chí. Tuy nhiên, “đầu tiên” và “cuối cùng” phụ thuộc vào thứ tự duyệt của collection; chúng không tự sắp xếp dữ liệu theo một property.

## 1. Ba dạng selection cần phân biệt

| Toán tử | Ý nghĩa | Kết quả |
|---|---|---|
| `.?[condition]` | Lấy tất cả phần tử thỏa điều kiện | Collection chứa các phần tử phù hợp |
| `.^[condition]` | Lấy phần tử phù hợp đầu tiên | Một phần tử, hoặc null nếu không tìm thấy |
| `.$[condition]` | Lấy phần tử phù hợp cuối cùng | Một phần tử, hoặc null nếu không tìm thấy |

Ví dụ với danh sách:

    #members.?[nationality == 'Serbian']
    #members.^[nationality == 'Serbian']
    #members.$[nationality == 'Serbian']

Biểu thức thứ nhất trả về tất cả thành viên có quốc tịch Serbian. Biểu thức thứ hai trả về thành viên đầu tiên thỏa điều kiện, còn biểu thức thứ ba trả về thành viên cuối cùng thỏa điều kiện.

Cú pháp predicate nằm trong cặp ngoặc vuông. Predicate phải đánh giá thành Boolean; nếu expression bên trong trả về kiểu khác, SpEL báo lỗi đánh giá thay vì tự suy đoán điều kiện đúng/sai.

## 2. First selection trên List và Iterable

Với một List hoặc đối tượng triển khai `java.lang.Iterable`, SpEL đánh giá predicate lần lượt trên từng phần tử. First selection dừng khi tìm thấy phần tử đầu tiên phù hợp và trả về chính phần tử đó.

Ví dụ:

    List<Inventor> members = List.of(
            new Inventor("Nikola Tesla", "Serbian"),
            new Inventor("Thomas Edison", "American"),
            new Inventor("Mihajlo Pupin", "Serbian")
    );

    StandardEvaluationContext context =
            new StandardEvaluationContext();
    context.setVariable("members", members);

    ExpressionParser parser = new SpelExpressionParser();

    Inventor firstSerbian = parser.parseExpression(
            "#members.^[nationality == 'Serbian']"
    ).getValue(context, Inventor.class);

Kết quả là Nikola Tesla vì đó là phần tử đầu tiên trong danh sách có `nationality` bằng `'Serbian'`.

Trong predicate, có thể truy cập property trực tiếp trên phần tử hiện tại:

    #members.^[nationality == 'Serbian']

Hoặc dùng `#this` để thể hiện rõ đối tượng đang được xét:

    #members.^[#this.nationality == 'Serbian']

Cả hai cách đều diễn đạt cùng điều kiện. Khi predicate có nhiều thao tác hoặc lồng nhau, `#this` giúp người đọc nhận ra property thuộc phần tử hiện tại.

## 3. Last selection trên List và Iterable

Last selection tiếp tục duyệt collection để tìm phần tử phù hợp cuối cùng. Kết quả là một phần tử đơn, không phải một List chỉ chứa một phần tử:

    Inventor lastSerbian = parser.parseExpression(
            "#members.$[nationality == 'Serbian']"
    ).getValue(context, Inventor.class);

Với danh sách ở ví dụ trên, kết quả là Mihajlo Pupin. Nếu có nhiều phần tử thỏa điều kiện, chỉ phần tử phù hợp cuối cùng được trả về.

Điểm khác biệt về cách duyệt:

- First selection có thể dừng ngay khi gặp phần tử phù hợp đầu tiên.
- Last selection cần duyệt hết collection để biết phần tử phù hợp nào xuất hiện cuối cùng.

Vì vậy, nếu collection lớn và phần tử phù hợp thường xuất hiện sớm, first selection có thể tránh việc duyệt các phần tử còn lại. Last selection phải tiếp tục kiểm tra cho đến cuối.

## 4. Selection trên Array

SpEL cũng hỗ trợ selection trên array. Predicate được đánh giá cho từng phần tử theo thứ tự index của array:

    String[] roles = {"GUEST", "EDITOR", "ADMIN", "EDITOR"};

    context.setVariable("roles", roles);

    String firstEditor = parser.parseExpression(
            "#roles.^[#this == 'EDITOR']"
    ).getValue(context, String.class);

    String lastEditor = parser.parseExpression(
            "#roles.$[#this == 'EDITOR']"
    ).getValue(context, String.class);

Cả hai kết quả đều là chuỗi `'EDITOR'`, nhưng chúng tương ứng với hai vị trí khác nhau trong array. Nếu cần xác định index của phần tử được tìm thấy, first/last selection không trả về index; hãy dùng một vòng lặp hoặc xử lý collection trong Java khi cần cả vị trí và giá trị.

## 5. Selection trên Map

Với Map, predicate được đánh giá trên từng entry kiểu `Map.Entry`. Trong predicate có thể truy cập hai property đặc biệt:

- `key`: khóa của entry hiện tại.
- `value`: giá trị của entry hiện tại.

Ví dụ:

    #scores.?[value >= 80]
    #scores.^[value >= 80]
    #scores.$[value >= 80]

Selection thông thường trả về Map chứa tất cả entry phù hợp. First selection và last selection trả về Map chỉ chứa entry phù hợp đầu tiên hoặc cuối cùng, không trả trực tiếp về value của entry.

Ví dụ với Map có thứ tự:

    Map<String, Integer> scores = new LinkedHashMap<>();
    scores.put("Lan", 75);
    scores.put("Minh", 92);
    scores.put("An", 88);

    context.setVariable("scores", scores);

    Map<?, ?> firstPassed = parser.parseExpression(
            "#scores.^[value >= 80]"
    ).getValue(context, Map.class);

Kết quả là Map một entry: `{"Minh": 92}`. Nếu cần lấy riêng value, có thể truy cập key đã biết hoặc xử lý Map kết quả trong Java. Với Map một entry, không nên giả định thứ tự hoặc cách lấy phần tử từ một Map implementation tùy ý nếu ứng dụng yêu cầu xử lý tổng quát.

Để tìm theo key, predicate có thể dùng:

    #scores.^[key == 'Minh']

Để tìm theo cả key và value:

    #scores.$[key != 'Lan' and value >= 80]

## 6. “Đầu tiên” và “cuối cùng” phụ thuộc thứ tự duyệt

First/last selection không có nghĩa là tìm giá trị nhỏ nhất/lớn nhất. Nó chỉ chọn phần tử đầu hoặc cuối trong thứ tự iteration của collection sau khi áp dụng predicate.

Với các cấu trúc dữ liệu thường gặp:

| Kiểu collection | Thứ tự dùng để xác định first/last |
|---|---|
| List | Thứ tự index từ đầu đến cuối |
| Array | Thứ tự index từ 0 đến length - 1 |
| LinkedHashSet | Thứ tự insertion |
| TreeSet | Thứ tự comparator |
| LinkedHashMap | Thứ tự iteration theo insertion |
| TreeMap | Thứ tự theo comparator của key |
| HashSet / HashMap | Không nên dựa vào thứ tự iteration ổn định |

Nếu cần phần tử có timestamp sớm nhất, điểm cao nhất hoặc giá trị lớn nhất, hãy sắp xếp collection theo tiêu chí đó trước khi dùng first/last selection, hoặc tính kết quả bằng Java. Ví dụ, `members.$[score > 80]` không tìm người có score cao nhất; nó chỉ tìm người thỏa điều kiện xuất hiện cuối trong thứ tự duyệt.

Đối với HashMap hoặc HashSet, thứ tự duyệt không được bảo đảm theo insertion. Vì vậy, kết quả first/last có thể không phù hợp nếu nghiệp vụ yêu cầu tính xác định. Hãy dùng collection có thứ tự rõ ràng hoặc chuẩn bị dữ liệu trước khi đánh giá.

## 7. Không tìm thấy phần tử phù hợp

Với first selection và last selection, nếu không có phần tử nào thỏa predicate, kết quả là null. Điều này khác với all-match selection `.?[...]`, vốn trả về collection rỗng khi không có phần tử phù hợp.

Ví dụ:

    Inventor selected = parser.parseExpression(
            "#members.^[nationality == 'Martian']"
    ).getValue(context, Inventor.class);

Nếu không có thành viên nào phù hợp, `selected` là null. Hãy kiểm tra null trước khi truy cập property tiếp theo:

    #members.^[nationality == 'Serbian']?.name

Safe navigation trên kết quả được chọn giúp tránh lỗi khi không có phần tử phù hợp. Có thể dùng Elvis operator để cung cấp giá trị mặc định:

    #members.^[nationality == 'Serbian']?.name ?: 'Unknown'

Trong ví dụ trên, nếu không tìm thấy thành viên hoặc tên là null, biểu thức trả về `'Unknown'`.

Cần phân biệt hai trường hợp: collection không có phần tử phù hợp và collection ban đầu là null. Selection thông thường trên target null sẽ gây lỗi đánh giá. Các toán tử null-safe selection như `?.^` và `?.$` được hỗ trợ từ Spring Framework 6.1.6; chúng cho phép biểu thức trả về null khi target collection null:

    #members?.^[nationality == 'Serbian']
    #members?.$[nationality == 'Serbian']

Nếu phiên bản Spring đang dùng chưa hỗ trợ cú pháp null-safe selection, hãy kiểm tra collection trước trong Java hoặc trong biểu thức bằng điều kiện phù hợp.

## 8. Kết hợp first/last selection với property và method

Kết quả first/last selection có thể tiếp tục được dùng để đọc property hoặc gọi method:

    #members.^[nationality == 'Serbian']?.name
    #members.$[nationality == 'Serbian']?.getDisplayName()

Có thể tiếp tục truy cập sâu hơn nếu object được tìm thấy:

    #orders.^[status == 'PAID']?.customer?.email

Biểu thức này tìm đơn hàng đã thanh toán đầu tiên, sau đó lấy email khách hàng. Safe navigation xử lý trường hợp không tìm thấy đơn hàng hoặc customer là null. Nếu method được gọi có side effect, hãy nhớ rằng mỗi lần đánh giá Expression có thể thực hiện lời gọi đó.

Có thể kết hợp selection với projection. Ví dụ, sau khi tìm phần tử đầu tiên phù hợp, lấy một property từ kết quả:

    #members.^[active]?.department

Projection `.![...]` thường được dùng khi cần biến đổi từng phần tử trong collection; first/last selection chỉ chọn một phần tử phù hợp.

## 9. Kiểm tra predicate và hiệu năng

Predicate của selection cần trả về Boolean. Các biểu thức so sánh thường dùng gồm `==`, `!=`, `>`, `>=`, `<` và `<=`. Có thể kết hợp điều kiện bằng `and`, `or`, `not` và dấu ngoặc:

    #orders.^[
        status == 'PAID' and
        total >= 100 and
        customer.active
    ]

Với predicate phức tạp, hãy đặt ngoặc và thụt lề rõ ràng. Nếu predicate gọi method, cần bảo đảm method có tính chất phù hợp khi được gọi nhiều lần trên các phần tử.

First selection dừng tại phần tử đầu tiên phù hợp; last selection cần duyệt hết nguồn để xác định kết quả cuối. Cả hai đều đánh giá predicate theo từng phần tử cho đến khi có kết quả hoặc hết collection. Không nên dùng selection để thay thế một truy vấn database lớn nếu có thể đẩy điều kiện lọc xuống tầng repository.

## 10. Ví dụ đầy đủ trong Java

Ví dụ dưới đây tìm thành viên đang hoạt động đầu tiên và cuối cùng trong một danh sách:

    public class Member {
        private String name;
        private boolean active;

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

    List<Member> members = List.of(
            new Member("Lan", false),
            new Member("Minh", true),
            new Member("An", true)
    );

    StandardEvaluationContext context =
            new StandardEvaluationContext();
    context.setVariable("members", members);

    ExpressionParser parser = new SpelExpressionParser();

    Member firstActive = parser.parseExpression(
            "#members.^[active]"
    ).getValue(context, Member.class);

    Member lastActive = parser.parseExpression(
            "#members.$[active]"
    ).getValue(context, Member.class);

Kết quả `firstActive` là Minh, còn `lastActive` là An. Ví dụ cho thấy cả hai toán tử dùng cùng một predicate nhưng chọn phần tử theo hai vị trí khác nhau trong thứ tự list.

Trong unit test, nên bao phủ ít nhất các trường hợp: phần tử đầu tiên phù hợp, nhiều phần tử phù hợp, chỉ phần tử cuối phù hợp, không có phần tử phù hợp, collection rỗng và collection null. Với Map, hãy kiểm tra cả key, value và thứ tự iteration của implementation được sử dụng.

## 11. Ghi nhớ

Dùng `.^[condition]` để lấy phần tử đầu tiên phù hợp và `.$[condition]` để lấy phần tử cuối cùng. Với List, Iterable và array, kết quả là phần tử được chọn; với Map, kết quả là Map chứa entry được chọn. Nếu không có phần tử phù hợp, first/last selection trả về null, trong khi all-match selection trả về collection rỗng. Kết quả phụ thuộc thứ tự duyệt của nguồn, không tự tìm min/max. Hãy kiểm tra null, chọn collection có thứ tự xác định khi cần kết quả ổn định và dùng selection trong SpEL cho các collection đã có sẵn trong context.
