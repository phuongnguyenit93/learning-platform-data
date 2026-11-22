# Tạo mảng inline trong SpEL

SpEL có thể tạo dữ liệu collection ngay trong biểu thức. Tuy nhiên, cần phân biệt inline list với mảng Java thực sự. Cú pháp {1, 2, 3} tạo một List; cú pháp new int[]{1, 2, 3} tạo một mảng kiểu int[]. Hai kết quả có thể chứa cùng các giá trị nhưng khác kiểu dữ liệu và có hành vi khác nhau khi truyền cho Java method, gán vào property hoặc xử lý tiếp trong biểu thức.

Khi cần một cấu trúc có kiểu phần tử và kích thước cố định, hãy tạo array. Khi cần một danh sách linh hoạt để lọc, duyệt hoặc bổ sung phần tử, inline list thường phù hợp hơn.

## 1. Phân biệt inline list và Java array

Inline list trong SpEL dùng dấu ngoặc nhọn:

    {10, 20, 30}

Biểu thức này tạo một đối tượng List chứa ba phần tử. Nó không tự trở thành int[] chỉ vì các phần tử đều là số nguyên.

Để tạo mảng Java, dùng toán tử new với kiểu phần tử và dấu ngoặc vuông:

    new int[]{10, 20, 30}

Kết quả là một mảng primitive int[]. Với kiểu tham chiếu, ví dụ mảng String:

    new java.lang.String[]{'SPRING', 'SpEL'}

Kết quả là một mảng String[].

So sánh:

| Biểu thức | Kiểu kết quả | Đặc điểm |
|---|---|---|
| {10, 20, 30} | List | Collection có thể thay đổi kích thước |
| new int[]{10, 20, 30} | int[] | Mảng primitive, kích thước cố định |
| new java.lang.String[]{'A', 'B'} | String[] | Mảng tham chiếu, kích thước cố định |
| new int[3] | int[] | Mảng ba phần tử, ban đầu mỗi phần tử bằng 0 |
| new java.lang.String[2] | String[] | Mảng hai phần tử, ban đầu mỗi phần tử là null |

Việc chọn cú pháp phụ thuộc vào kiểu mà phần Java phía sau mong đợi. Nếu một method nhận int[], truyền inline list có thể không đáp ứng đúng hợp đồng kiểu. Hãy tạo đúng mảng hoặc chuyển đổi rõ ràng trước khi gọi method.

## 2. Cú pháp tạo mảng có phần tử khởi tạo

Cú pháp cơ bản:

    new elementType[]{value1, value2, value3}

Trong đó:

- new yêu cầu SpEL tạo một đối tượng mới.
- elementType là kiểu của từng phần tử trong mảng.
- [] khai báo rằng kết quả là một mảng.
- {...} chứa các giá trị ban đầu theo thứ tự.

Ví dụ mảng số nguyên:

    new int[]{3, 5, 8, 13}

Mảng số thực:

    new double[]{1.5, 2.0, 3.75}

Mảng Boolean:

    new boolean[]{true, false, true}

Mảng chuỗi:

    new java.lang.String[]{'ACTIVE', 'PENDING', 'CLOSED'}

Số phần tử trong phần khởi tạo quyết định độ dài mảng. Vì vậy, new int[]{} tạo mảng int rỗng có độ dài bằng 0. Nếu cần khai báo độ dài mà chưa có giá trị khởi tạo, dùng cú pháp tạo mảng theo kích thước.

Tên kiểu có thể là kiểu primitive như int, long, double, boolean hoặc kiểu tham chiếu như java.lang.String, java.time.LocalDate và các lớp trong ứng dụng. Với lớp ngoài java.lang, hãy dùng tên đầy đủ để TypeLocator phân giải chính xác.

## 3. Tạo mảng theo kích thước

SpEL hỗ trợ tạo mảng với kích thước xác định:

    new int[3]

Kết quả là mảng int có ba vị trí. Các phần tử primitive được khởi tạo bằng giá trị mặc định của kiểu:

- Kiểu số nguyên như byte, short, int và long có giá trị mặc định là 0.
- Kiểu số thực như float và double có giá trị mặc định là 0.0.
- boolean có giá trị mặc định là false.
- char có giá trị mặc định là ký tự null.

Với mảng kiểu tham chiếu:

    new java.lang.String[2]

hai phần tử ban đầu đều là null. Java không tự tạo hai chuỗi rỗng.

Cú pháp tạo mảng theo kích thước và cú pháp khởi tạo phần tử phục vụ hai mục đích khác nhau:

    new int[3]

    new int[]{10, 20, 30}

Cách đầu tạo các vị trí với giá trị mặc định. Cách thứ hai tạo mảng và điền ba giá trị đã chỉ định. Không viết kích thước tường minh cùng danh sách khởi tạo như new int[3]{10, 20, 30}; hãy chọn một trong hai dạng cú pháp.

Kích thước mảng phải là số nguyên không âm. Kích thước âm hoặc biểu thức kích thước không hợp lệ sẽ khiến quá trình đánh giá thất bại.

## 4. Mảng primitive và mảng kiểu tham chiếu

Mảng primitive lưu trực tiếp giá trị primitive:

    new int[]{10, 20, 30}
    new boolean[]{true, false}

Mảng kiểu tham chiếu lưu các tham chiếu đến object:

    new java.lang.String[]{'Spring', 'Framework'}
    new java.math.BigDecimal[]{
        new java.math.BigDecimal('10.50'),
        new java.math.BigDecimal('20.00')
    }

Khác biệt này ảnh hưởng đến giá trị phần tử và khả năng chứa null:

| Đặc điểm | Mảng primitive | Mảng tham chiếu |
|---|---|---|
| Ví dụ | int[], boolean[] | String[], BigDecimal[] |
| Giá trị phần tử | Giá trị primitive | Tham chiếu đến object |
| Có thể chứa null | Không | Có |
| Giá trị mặc định | 0, false, 0.0... | null |
| Kiểu phần tử | Cố định theo primitive đã khai báo | Cố định theo class đã khai báo |

Nếu một phần tử đầu vào có thể null, không thể lưu nó vào mảng primitive. Trong trường hợp cần biểu diễn dữ liệu thiếu, hãy cân nhắc dùng kiểu wrapper như Integer[] thay vì int[]:

    new java.lang.Integer[]{1, null, 3}

Mảng này có thể chứa null ở vị trí thứ hai. Với int[], mỗi vị trí luôn có một giá trị số nguyên primitive.

## 5. Giá trị khởi tạo phải phù hợp với kiểu phần tử

Khi tạo mảng, mỗi phần tử phải tương thích với kiểu phần tử đã khai báo. Ví dụ:

    new int[]{1, 2, 3}
    new java.lang.String[]{'A', 'B'}

Không thể tạo một int[] chứa chuỗi tùy ý:

    new int[]{1, 'two', 3}

Giá trị không thể chuyển đổi sang kiểu phần tử sẽ gây lỗi khi đánh giá biểu thức. SpEL có cơ chế chuyển đổi kiểu trong những ngữ cảnh phù hợp, nhưng không nên dựa vào các phép chuyển đổi ngầm không rõ ràng để định nghĩa dữ liệu đầu vào.

Nếu dữ liệu ban đầu đến từ cấu hình hoặc người dùng, hãy xác thực và chuyển đổi ở tầng Java trước khi tạo mảng. Với các kiểu số, ngày tháng hoặc kiểu domain, nên dùng literal và constructor rõ ràng để người đọc thấy chính xác kiểu dữ liệu được tạo ra.

Ví dụ tạo mảng BigDecimal:

    new java.math.BigDecimal[]{
        new java.math.BigDecimal('12.50'),
        new java.math.BigDecimal('99.90')
    }

Cách viết này tạo hai đối tượng BigDecimal, sau đó đặt chúng vào mảng BigDecimal[].

## 6. Truy cập phần tử của mảng

Sau khi tạo mảng, có thể truy cập phần tử bằng chỉ số trong dấu ngoặc vuông:

    new int[]{10, 20, 30}[0]

Biểu thức trên trả về 10. Chỉ số mảng bắt đầu từ 0, giống Java:

    new int[]{10, 20, 30}[1]

trả về 20.

Trong thực tế, thường lưu kết quả mảng vào một biến context hoặc property của root object, sau đó truy cập:

    #codes[0]
    #codes[1]

Nếu chỉ số âm hoặc lớn hơn chỉ số cuối cùng, SpEL không thể lấy phần tử và sẽ phát sinh lỗi đánh giá. Trước khi truy cập một vị trí được tính động, cần bảo đảm mảng không null và chỉ số nằm trong phạm vi.

Mảng có kích thước cố định sau khi tạo. Có thể thay đổi giá trị tại một vị trí nếu có quyền ghi phù hợp, nhưng không thể thêm hoặc xóa phần tử làm thay đổi độ dài mảng. Nếu cần thao tác thay đổi kích thước, hãy dùng List.

## 7. Dùng mảng inline trong cấu hình Spring

Một trường hợp sử dụng phổ biến là khởi tạo mảng cho property của bean bằng @Value và SpEL:

    @Component
    public class RetrySettings {

        private final int[] retryDelays;

        public RetrySettings(
                @Value("#{new int[]{100, 500, 1000}}")
                int[] retryDelays) {
            this.retryDelays = retryDelays;
        }

        public int[] getRetryDelays() {
            return retryDelays;
        }
    }

Biểu thức nằm trong #{...} vì @Value đang yêu cầu Spring phân tích một SpEL expression. Bên trong dấu #{...}, cú pháp new int[]{...} tạo mảng int thực sự và Spring chuyển kết quả vào tham số constructor có kiểu int[].

Có thể dùng mảng tham chiếu tương tự:

    @Value("#{new java.lang.String[]{'VN', 'SG', 'TH'}}")
    private String[] supportedRegions;

Mảng phù hợp khi cấu hình có số lượng phần tử ổn định và bean cần đúng kiểu array. Nếu danh sách cần thay đổi linh hoạt hoặc cần thao tác thêm/bớt, cân nhắc bind cấu hình thành List bằng cơ chế configuration properties.

Không nên đưa các giá trị cấu hình quan trọng vào chuỗi SpEL cố định nếu chúng cần thay đổi độc lập. Trong trường hợp đó, hãy dùng property source hoặc configuration properties để quản lý dữ liệu; SpEL chỉ nên đảm nhiệm phần biểu thức thực sự cần thiết.

## 8. Đánh giá mảng inline bằng ExpressionParser

Có thể tạo và đánh giá mảng trực tiếp trong Java:

    ExpressionParser parser = new SpelExpressionParser();

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    Expression expression =
            parser.parseExpression("new int[]{10, 20, 30}");

    int[] values = expression.getValue(context, int[].class);

    int firstValue = values[0];

StandardEvaluationContext được sử dụng vì cú pháp new là tính năng tạo đối tượng của SpEL. SimpleEvaluationContext chủ ý giới hạn các tính năng nâng cao và không hỗ trợ constructor references như context tiêu chuẩn.

Nếu chỉ tạo inline list:

    Expression listExpression =
            parser.parseExpression("{10, 20, 30}");

    java.util.List<?> values =
            listExpression.getValue(context, java.util.List.class);

thì kết quả là List chứ không phải int[]. Kiểu đích trong getValue giúp Java nhận đúng kiểu kết quả mà ứng dụng mong đợi.

Trong ứng dụng thật, hãy parse biểu thức cấu hình một lần khi khởi tạo hoặc nạp rule, sau đó tái sử dụng Expression. Không cần tạo lại parser và parse cùng một chuỗi trong mỗi request nếu biểu thức không thay đổi.

## 9. Mảng lồng nhau và cấu trúc nhiều chiều

Java hỗ trợ mảng nhiều chiều bằng cách dùng nhiều cặp ngoặc vuông trong khai báo kiểu. Với SpEL, khi cần biểu diễn dữ liệu dạng ma trận, hãy xác định rõ kiểu phần tử và từng chiều trước khi sử dụng.

Ví dụ tạo một mảng hai chiều có hai hàng và ba cột:

    new int[2][3]

Mỗi phần tử của mảng ngoài là một mảng int có ba phần tử. Các giá trị ban đầu là 0.

Nếu dữ liệu có cấu trúc không đều, chẳng hạn mỗi hàng có số phần tử khác nhau, Java biểu diễn nó bằng mảng của các mảng. Trong tình huống đó, cần khởi tạo và kiểm tra từng hàng phù hợp với dữ liệu thực tế. Không nên giả định mọi hàng đều có cùng độ dài chỉ vì biến được khai báo là mảng hai chiều.

Đối với dữ liệu lồng nhau chỉ cần duyệt hoặc lọc, inline list lồng nhau có thể dễ đọc hơn. Chỉ tạo mảng nhiều chiều khi hợp đồng Java thực sự yêu cầu kiểu array và kích thước từng chiều đã được xác định.

## 10. Chọn array hay List?

| Tiêu chí | Array | List |
|---|---|---|
| Kiểu dữ liệu | Kiểu phần tử cố định | Collection chứa object |
| Kích thước | Cố định sau khi tạo | Có thể thay đổi với List mutable |
| Truy cập phần tử | Dùng [index] | Dùng [index] trong SpEL hoặc get(index) |
| Thêm/xóa phần tử | Không thay đổi được độ dài | Có thể hỗ trợ add/remove tùy implementation |
| Primitive | Có thể dùng trực tiếp int[], double[] | List chứa wrapper như Integer, Double |
| Truyền vào Java API | Phù hợp tham số array | Phù hợp tham số Collection/List |

Hãy dùng array khi cần kiểu cụ thể như int[], byte[] hoặc String[], hoặc khi API nhận tham số array. Dùng List khi cần thao tác collection linh hoạt, lọc và biến đổi dữ liệu hoặc khi số lượng phần tử có thể thay đổi.

Không nên chọn array chỉ vì cú pháp trông giống Java hơn. Hãy dựa vào kiểu mà thành phần nhận kết quả cần sử dụng.

## 11. Lỗi thường gặp khi tạo mảng inline

| Cách viết hoặc tình huống | Nguyên nhân | Hướng xử lý |
|---|---|---|
| {1, 2, 3} nhưng Java mong đợi int[] | Inline list tạo List | Dùng new int[]{1, 2, 3} |
| new int[3]{1, 2, 3} | Trộn cú pháp kích thước và initializer | Dùng new int[]{1, 2, 3} |
| new int[]{1, 'two'} | Phần tử không tương thích kiểu int | Chuyển đổi và xác thực dữ liệu trước |
| new int[-1] | Kích thước âm | Kiểm tra kích thước không âm |
| #codes[5] với mảng chỉ có ba phần tử | Chỉ số vượt phạm vi | Kiểm tra độ dài trước khi truy cập |
| Gán null vào phần tử int[] | Primitive không chứa null | Dùng Integer[] nếu null là trạng thái hợp lệ |
| Tạo mảng bằng new trong SimpleEvaluationContext | Context không hỗ trợ constructor references | Dùng context phù hợp và giới hạn quyền truy cập |

Khi lỗi xuất hiện, cần xác định lỗi xảy ra ở bước parse hay evaluate. Lỗi cú pháp thường liên quan đến dấu ngoặc, kiểu hoặc initializer. Lỗi đánh giá có thể liên quan đến chuyển đổi phần tử, kích thước, quyền tạo đối tượng hoặc truy cập chỉ số.

## 12. Kiểm soát an toàn khi dùng toán tử new

Tạo mảng inline dùng cú pháp new của SpEL. Toán tử new cũng có thể được dùng để gọi constructor của lớp Java. Vì vậy, biểu thức không đáng tin cậy có thể mở rộng quyền tạo đối tượng nếu được đánh giá trong một context có khả năng rộng.

Một số nguyên tắc:

- Chỉ đánh giá biểu thức do ứng dụng hoặc nguồn cấu hình đáng tin cậy kiểm soát.
- Không nhận nguyên chuỗi SpEL từ người dùng bên ngoài rồi đánh giá tùy ý.
- Dùng kiểu phần tử đã xác định, tránh cho phép biểu thức chọn lớp tùy ý.
- Chọn EvaluationContext với tập tính năng tối thiểu đáp ứng nhu cầu.
- Kiểm tra kích thước và dữ liệu phần tử trước khi tạo mảng lớn.
- Xử lý rõ lỗi parse, lỗi chuyển đổi và lỗi cấp phát bộ nhớ.

Mảng kích thước lớn có thể tiêu tốn bộ nhớ đáng kể. Nếu kích thước đến từ dữ liệu động, hãy đặt giới hạn nghiệp vụ ở Java trước khi đưa giá trị vào biểu thức.

## Kết luận

Để tạo mảng Java inline trong SpEL, dùng cú pháp new elementType[]{...} khi muốn khởi tạo các phần tử cụ thể, hoặc new elementType[size] khi muốn tạo mảng theo kích thước và nhận giá trị mặc định. Cú pháp {...} đơn thuần tạo inline List, không phải Java array.

Kiểu phần tử quyết định mảng có thể chứa dữ liệu nào: primitive không chứa null, còn mảng tham chiếu có thể chứa null. Sau khi tạo, mảng có kích thước cố định và truy cập bằng chỉ số bắt đầu từ 0. Hãy chọn array khi Java API yêu cầu đúng kiểu mảng; nếu cần collection linh hoạt, hãy dùng List. Khi đánh giá biểu thức có toán tử new, chọn context phù hợp và chỉ xử lý biểu thức từ nguồn đáng tin cậy.