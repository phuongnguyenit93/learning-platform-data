# Biến, phạm vi, khởi tạo và ràng buộc gán của final

Trong Java 27, biến là tên gắn với một giá trị có kiểu xác định. Khi khai báo biến, chương trình xác định kiểu và phạm vi sử dụng của biến; khi khởi tạo hoặc gán, chương trình cung cấp giá trị cho biến đó. Từ khóa **final** đặt thêm ràng buộc rằng một biến chỉ được gán một lần.

Hiểu rõ cách khai báo, phạm vi, khởi tạo và gán biến giúp tránh lỗi biên dịch, kiểm soát trạng thái của đối tượng và viết mã dễ đọc hơn. Các quy tắc dưới đây là quy tắc ngôn ngữ Java đang áp dụng trong JDK 27.

## 1. Khai báo và sử dụng biến

Một khai báo biến cục bộ thường có dạng:

~~~java
int age = 27;
String language = "Java";
~~~

Trong đó:

- **int** và **String** là kiểu của biến.
- **age** và **language** là tên biến.
- Phần bên phải dấu bằng cung cấp giá trị khởi tạo.

Java là ngôn ngữ định kiểu tĩnh: kiểu của biến được xác định khi biên dịch. Một biến đã khai báo với kiểu **int** không thể được gán một đối tượng **String**.

~~~java
int count = 10;
count = 12;       // Hợp lệ: giá trị mới vẫn có kiểu int
// count = "twelve"; // Lỗi biên dịch: String không phải int
~~~

Có thể khai báo biến trước rồi khởi tạo sau, miễn là biến được gán giá trị trước khi chương trình đọc nó:

~~~java
int result;
result = 42;
System.out.println(result);
~~~

Cần phân biệt ba thao tác:

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| Khai báo (declaration) | Giới thiệu tên và kiểu biến | **int score;** |
| Khởi tạo (initialization) | Gán giá trị đầu tiên cho biến | **int score = 10;** |
| Gán lại (reassignment) | Thay giá trị của biến đã được khởi tạo | **score = 15;** |

### Suy luận kiểu với var

Với biến cục bộ, Java hỗ trợ từ khóa **var** để trình biên dịch suy luận kiểu từ biểu thức khởi tạo:

~~~java
var message = "Hello, Java";
var total = 27;
~~~

Ở đây, **message** có kiểu **String**, còn **total** có kiểu **int**. **var** không làm Java trở thành ngôn ngữ định kiểu động; kiểu vẫn được xác định tại thời điểm biên dịch.

**var** chỉ dùng trong các ngữ cảnh khai báo biến cục bộ được ngôn ngữ cho phép. Với khai báo biến cục bộ thông thường, cần có biểu thức khởi tạo để suy luận kiểu. **var** cũng được dùng cho biến của vòng lặp **enhanced for** và biến tài nguyên trong **try-with-resources**, theo quy tắc suy luận kiểu của từng ngữ cảnh. Không dùng **var** để khai báo field, tham số phương thức hoặc kiểu trả về.

Ví dụ với vòng lặp **enhanced for**:

~~~java
for (var language : java.util.List.of("Java", "Kotlin")) {
    System.out.println(language);
}
~~~

Có thể kết hợp **var** với **final**:

~~~java
final var language = "Java";
~~~

Biến **language** được suy luận là **String** và không thể được gán lại.

## 2. Các loại biến và phạm vi sử dụng

Java có các nhóm biến thường gặp sau:

- **Biến cục bộ (local variable):** được khai báo trong thân phương thức, constructor, block hoặc một cấu trúc điều khiển.
- **Tham số (parameter):** nhận giá trị truyền vào khi gọi phương thức, constructor hoặc lambda.
- **Biến instance (instance field):** thuộc về một đối tượng; mỗi đối tượng có trạng thái field riêng.
- **Biến static (static field):** thuộc về lớp; các đối tượng của lớp dùng chung một field static.

Ví dụ:

~~~java
class Counter {
    private int value;                 // Instance field
    private static int createdCount;   // Static field

    Counter(int initialValue) {        // initialValue là parameter
        value = initialValue;
        createdCount++;
    }

    void increment(int amount) {       // amount là parameter
        int nextValue = value + amount; // Local variable
        value = nextValue;
    }
}
~~~

### Phạm vi của biến cục bộ

Phạm vi (scope) là vùng mã nguồn mà tên biến có thể được sử dụng trực tiếp. Với biến cục bộ được khai báo trong một block, phạm vi bắt đầu tại khai báo và kéo dài đến hết block đó.

~~~java
void calculate() {
    int base = 10;

    if (base > 0) {
        int bonus = 5;
        int result = base + bonus;
        System.out.println(result);
    }

    // base vẫn nằm trong phạm vi ở đây.
    // bonus và result đã ra khỏi phạm vi.
}
~~~

Một cặp dấu ngoặc nhọn tạo ra block mới. Biến khai báo trong block bên trong không thể được sử dụng sau khi block kết thúc.

Biến khai báo trong phần khởi tạo của vòng lặp **for** chỉ có phạm vi trong câu lệnh **for** đó:

~~~java
for (int index = 0; index < 3; index++) {
    System.out.println(index);
}

// index không còn trong phạm vi tại đây.
~~~

Tham số phương thức có phạm vi trong thân phương thức hoặc constructor tương ứng. Tham số lambda có phạm vi trong thân lambda:

~~~java
java.util.function.IntUnaryOperator doubleValue =
        number -> number * 2;
~~~

Tham số **number** chỉ được sử dụng trong biểu thức lambda này.

Biến khai báo trong khối **catch** chỉ được sử dụng trong khối catch tương ứng. Tương tự, biến tài nguyên được khai báo trong phần tài nguyên của **try-with-resources** có phạm vi trong phần khai báo tài nguyên và thân **try** tương ứng.

### Phạm vi của field

Field được khai báo trong thân lớp và có thể được sử dụng trong các phương thức hoặc constructor của lớp theo quy tắc truy cập của Java.

~~~java
class Account {
    private int balance;

    void deposit(int amount) {
        balance += amount;
    }

    int getBalance() {
        return balance;
    }
}
~~~

Field **balance** là trạng thái của từng đối tượng **Account**. Mỗi đối tượng có giá trị riêng. Nếu field được khai báo **static**, field thuộc về lớp và được dùng chung:

~~~java
class Account {
    private static int accountCount;
}
~~~

Phạm vi tên và quyền truy cập là hai khái niệm khác nhau. Phạm vi xác định tên có thể xuất hiện ở đâu trong mã nguồn; các modifier như **private**, **protected** và **public** xác định mã nào được phép truy cập thành viên theo quy tắc truy cập của Java.

### Che khuất tên biến (shadowing)

Một biến cục bộ hoặc tham số có thể trùng tên với field. Khi đó, tên không định danh trong phương thức sẽ tham chiếu tới biến cục bộ hoặc tham số gần nhất. Dùng **this** để chỉ rõ field của đối tượng hiện tại:

~~~java
class Person {
    private String name;

    Person(String name) {
        this.name = name;
    }

    void rename(String name) {
        this.name = name;
    }
}
~~~

Trong constructor và phương thức trên, **name** là tham số; **this.name** là field.

Java không cho phép khai báo lại một biến cục bộ bằng cùng tên với biến cục bộ hoặc tham số đang nằm trong phạm vi bao quanh. Quy tắc này giúp tránh nhập nhằng giữa các biến có cùng tên trong những block lồng nhau.

## 3. Khởi tạo biến và giá trị mặc định

Cách khởi tạo phụ thuộc vào loại biến.

### Field được gán giá trị mặc định

Khi một đối tượng được tạo hoặc một lớp được khởi tạo, các field nhận giá trị mặc định theo kiểu trước khi các giá trị khởi tạo tường minh và constructor hoàn tất quá trình khởi tạo.

| Kiểu field | Giá trị mặc định |
|---|---|
| **byte**, **short**, **int**, **long** | Số 0 tương ứng với kiểu |
| **float**, **double** | 0.0 tương ứng với kiểu |
| **char** | Ký tự NUL, mã Unicode 0 |
| **boolean** | **false** |
| Kiểu tham chiếu như **String**, mảng hoặc đối tượng | **null** |

Ví dụ:

~~~java
class Defaults {
    int number;
    boolean enabled;
    char marker;
    String name;

    void print() {
        System.out.println(number);  // 0
        System.out.println(enabled); // false
        System.out.println((int) marker); // 0
        System.out.println(name);    // null
    }
}
~~~

Các phần tử của mảng cũng được khởi tạo bằng giá trị mặc định tương ứng với kiểu phần tử:

~~~java
int[] values = new int[3];
// Các phần tử ban đầu đều bằng 0.
~~~

### Biến cục bộ phải được khởi tạo trước khi đọc

Biến cục bộ không tự nhận giá trị mặc định. Trình biên dịch yêu cầu chứng minh rằng biến đã được gán trên mọi đường đi có thể dẫn tới vị trí đọc biến.

~~~java
void printValue() {
    int value;
    // System.out.println(value); // Lỗi biên dịch: value chưa được khởi tạo

    value = 100;
    System.out.println(value);   // Hợp lệ
}
~~~

Quy tắc này được gọi là **definite assignment** (xác định chắc chắn đã được gán). Đây là kiểm tra tại thời điểm biên dịch, giúp phát hiện việc đọc biến cục bộ chưa có giá trị.

Ví dụ, khi gán trong các nhánh điều kiện, mọi nhánh có thể đi tới câu lệnh đọc đều phải cung cấp giá trị:

~~~java
void printTimeout(boolean useFastMode) {
    int timeout;

    if (useFastMode) {
        timeout = 5;
    } else {
        timeout = 30;
    }

    System.out.println(timeout);
}
~~~

Nếu bỏ nhánh **else**, trình biên dịch không thể chứng minh **timeout** đã được gán trong mọi trường hợp trước khi in ra, nên chương trình không biên dịch được.

### Khởi tạo field tường minh

Có thể gán giá trị cho field ngay tại nơi khai báo:

~~~java
class UserPreferences {
    private String language = "vi";
    private int pageSize = 20;
}
~~~

Hoặc gán trong constructor:

~~~java
class User {
    private String username;

    User(String username) {
        this.username = username;
    }
}
~~~

Khởi tạo ngay tại khai báo phù hợp với giá trị mặc định chung cho mọi đối tượng. Constructor phù hợp khi giá trị phụ thuộc vào dữ liệu truyền vào lúc tạo đối tượng.

## 4. Ràng buộc gán của final

Từ khóa **final** có thể áp dụng cho biến cục bộ, tham số và field. Khi một biến được khai báo **final**, biến đó chỉ được gán một lần. Sau khi đã được khởi tạo hoặc gán giá trị, không thể gán lại biến.

### final với biến cục bộ

Có thể khởi tạo ngay khi khai báo:

~~~java
final int maxAttempts = 3;
// maxAttempts = 5; // Lỗi biên dịch: không thể gán lại biến final
~~~

Cũng có thể khai báo một biến **final** trước rồi gán đúng một lần sau đó:

~~~java
final int port;
port = 8080;

System.out.println(port);
~~~

Trình biên dịch áp dụng quy tắc xác định chắc chắn đã được gán cho biến **final**. Nếu biến được đọc, Java phải chứng minh nó đã được gán trên mọi đường đi có thể tới vị trí đọc; đồng thời không được có đường đi gán biến lần thứ hai.

Ví dụ sau hợp lệ vì mỗi nhánh gán đúng một lần:

~~~java
final int retryLimit;

if (isProduction()) {
    retryLimit = 5;
} else {
    retryLimit = 2;
}

System.out.println(retryLimit);
~~~

Ví dụ sau không hợp lệ vì biến có thể được gán lần thứ hai:

~~~java
final int retryLimit = 3;
// retryLimit = 5; // Lỗi biên dịch
~~~

### final với field

Field **final** thường được dùng khi một giá trị phải được thiết lập trong quá trình tạo đối tượng và không thay đổi tham chiếu hoặc giá trị field sau đó.

~~~java
class ServerConfig {
    private final String host;
    private final int port;

    ServerConfig(String host, int port) {
        this.host = host;
        this.port = port;
    }
}
~~~

Các field **final** ở trên là blank final field: chúng được khai báo mà chưa khởi tạo tại chỗ. Mỗi constructor phải bảo đảm các field instance final được gán trước khi constructor kết thúc bình thường. Nếu có nhiều constructor, mỗi đường khởi tạo phải đáp ứng yêu cầu này; constructor có thể gọi constructor khác bằng **this(...)** để dùng chung logic khởi tạo.

Có thể khởi tạo field **final** ngay tại khai báo:

~~~java
class ApplicationInfo {
    private final String name = "Learning Platform";
}
~~~

Field **static final** có thể được khởi tạo tại nơi khai báo hoặc trong static initializer:

~~~java
class NetworkDefaults {
    static final int DEFAULT_PORT = 8080;

    static final String DEFAULT_HOST;

    static {
        DEFAULT_HOST = "localhost";
    }
}
~~~

Một blank static final field phải được gán trong static initializer trước khi quá trình khởi tạo lớp hoàn tất. Không thể gán lại field sau khi đã được khởi tạo.

### final với tham số

Tham số được khai báo **final** không thể bị gán lại bên trong phương thức hoặc constructor:

~~~java
void send(final String message) {
    System.out.println(message);
    // message = "Changed"; // Lỗi biên dịch
}
~~~

Điều này giúp bảo vệ liên kết giữa tên tham số và giá trị đầu vào trong phạm vi thân phương thức.

### final không làm đối tượng trở nên bất biến

Khi biến **final** chứa một tham chiếu, **final** khóa việc gán lại tham chiếu đó. Nó không tự động làm cho trạng thái của đối tượng được tham chiếu trở thành bất biến.

~~~java
import java.util.ArrayList;
import java.util.List;

class Example {
    void run() {
        final List<String> names = new ArrayList<>();

        names.add("An");       // Hợp lệ: thay đổi trạng thái đối tượng
        names.add("Binh");     // Hợp lệ

        // names = new ArrayList<>(); // Lỗi: gán lại tham chiếu final
    }
}
~~~

Trong ví dụ, biến **names** luôn tham chiếu tới cùng một đối tượng danh sách, nhưng nội dung danh sách vẫn có thể thay đổi. Muốn có một đối tượng bất biến, cần dùng kiểu dữ liệu và thiết kế API bảo đảm trạng thái của đối tượng không bị thay đổi; chỉ thêm **final** vào biến tham chiếu là chưa đủ.

## 5. Biến effectively final và lambda

Một biến cục bộ hoặc tham số được gọi là **effectively final** nếu nó không được khai báo bằng từ khóa **final**, nhưng sau khi khởi tạo không bị gán lại. Khái niệm này cho phép lambda và lớp cục bộ sử dụng biến mà không cần viết **final** tường minh.

~~~java
int multiplier = 2;

java.util.function.IntUnaryOperator scale =
        value -> value * multiplier;

System.out.println(scale.applyAsInt(5)); // 10
~~~

**multiplier** là effectively final vì sau khi khởi tạo bằng 2, chương trình không gán lại biến này.

Nếu thêm phép gán lại:

~~~java
int multiplier = 2;
multiplier = 3;

java.util.function.IntUnaryOperator scale =
        value -> value * multiplier;
~~~

Mã trên không biên dịch được vì **multiplier** đã bị gán lại và không còn effectively final. Biến cục bộ hoặc tham số được lambda sử dụng phải là **final** hoặc **effectively final**.

Quy tắc này áp dụng cho biến cục bộ và tham số được capture. Lambda vẫn có thể truy cập và thay đổi field thông qua đối tượng phù hợp; quy tắc effectively final của biến cục bộ không biến mọi field thành bất biến.

## 6. Biến hằng và static final

Một cách khai báo phổ biến cho giá trị cấu hình dùng chung là:

~~~java
class Limits {
    static final int MAX_CONNECTIONS = 100;
}
~~~

**static** cho biết field thuộc về lớp; **final** giới hạn việc gán field ở một lần khởi tạo. Theo quy ước đặt tên Java, các hằng thường được viết bằng chữ in hoa và phân tách từ bằng dấu gạch dưới.

Cần phân biệt field **static final** với *compile-time constant* (hằng số thời điểm biên dịch). Một biến chỉ là constant variable theo định nghĩa của Java khi nó là biến **final** có kiểu nguyên thủy hoặc **String**, được khởi tạo bằng biểu thức hằng tại thời điểm biên dịch.

Ví dụ:

~~~java
static final int MAX_USERS = 500;
static final String DEFAULT_LANGUAGE = "vi";
~~~

Ngược lại, field **static final** có kiểu tham chiếu như **List** không phải hằng số thời điểm biên dịch chỉ vì có hai modifier này. Nó vẫn là một tham chiếu được khởi tạo một lần; đối tượng được tham chiếu có thể vẫn thay đổi nếu kiểu đối tượng cho phép.

## 7. Phân biệt phạm vi, thời gian tồn tại và quyền truy cập

Ba khái niệm này liên quan nhưng không đồng nghĩa:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Phạm vi (scope) | Tên biến được sử dụng ở vùng mã nguồn nào? | Biến cục bộ trong block **if** chỉ dùng trong block đó |
| Thời gian tồn tại (lifetime) | Giá trị hoặc trạng thái biến tồn tại trong thời gian nào khi chương trình chạy? | Instance field gắn với vòng đời của đối tượng |
| Quyền truy cập (accessibility) | Mã nguồn nào được phép truy cập thành viên? | Field **private** được truy cập trực tiếp trong phạm vi được Java cho phép |

Phạm vi là quy tắc của ngôn ngữ và được kiểm tra khi biên dịch. Thời gian tồn tại liên quan tới quá trình thực thi và quản lý bộ nhớ. Không nên suy luận rằng mọi biến cục bộ nhất thiết tương ứng với một ô nhớ cố định trên stack; trình biên dịch và JVM có thể tối ưu cách lưu trữ miễn giữ nguyên hành vi quan sát được của chương trình.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Đọc biến cục bộ trước khi gán | Biến cục bộ không có giá trị mặc định | Khởi tạo tại khai báo hoặc bảo đảm mọi nhánh đều gán trước khi đọc |
| Gán lại biến **final** | Biến đã được khởi tạo hoặc gán trước đó | Chỉ gán một lần; nếu cần thay đổi giá trị, bỏ **final** |
| Field có giá trị **null** ngoài dự kiến | Field tham chiếu nhận mặc định **null** nếu chưa được khởi tạo tường minh | Khởi tạo field hoặc kiểm tra dữ liệu trước khi sử dụng |
| Không truy cập được biến sau block | Biến đã ra khỏi phạm vi khai báo | Khai báo biến ở block bao quanh nếu cần dùng ở phạm vi rộng hơn |
| Dùng nhầm field thay cho tham số | Tham số hoặc biến cục bộ che khuất tên field | Dùng **this.fieldName** để tham chiếu field |
| Lambda báo biến phải final hoặc effectively final | Biến cục bộ bị gán lại sau khi khởi tạo | Tạo giá trị ổn định để capture hoặc thiết kế lại phép tính |
| Nghĩ rằng danh sách không thể thay đổi vì tham chiếu là final | **final** chỉ ngăn gán lại biến tham chiếu | Dùng kiểu hoặc API bất biến nếu cần bảo vệ nội dung đối tượng |

Một số nguyên tắc thực hành:

- Khởi tạo biến cục bộ gần nơi sử dụng để người đọc dễ xác định nguồn gốc giá trị.
- Dùng phạm vi nhỏ nhất phù hợp với mục đích của biến để giảm trạng thái có thể bị thay đổi.
- Dùng **final** khi một biến chỉ nên nhận một giá trị trong suốt phạm vi của nó; điều này thể hiện rõ ý định và giúp trình biên dịch kiểm tra.
- Dùng **private final** cho field cần được thiết lập khi tạo đối tượng và không cần gán lại sau đó.
- Phân biệt tham chiếu final với đối tượng bất biến khi thiết kế dữ liệu.
- Khi một biến được lambda sử dụng, giữ nó effectively final nếu giá trị cần được capture ổn định.

## 9. Ví dụ tổng hợp

Ví dụ sau kết hợp field, tham số, biến cục bộ, phạm vi block và **final**:

~~~java
class Order {
    private final String orderId;
    private final int itemCount;
    private static final int MAX_ITEMS = 100;

    Order(String orderId, int itemCount) {
        if (itemCount < 0 || itemCount > MAX_ITEMS) {
            throw new IllegalArgumentException("Invalid item count");
        }

        this.orderId = orderId;
        this.itemCount = itemCount;
    }

    int calculateUnits(int multiplier) {
        final int baseUnits = itemCount;
        int totalUnits = baseUnits * multiplier;

        if (totalUnits > MAX_ITEMS) {
            int excess = totalUnits - MAX_ITEMS;
            System.out.println("Excess units: " + excess);
            totalUnits = MAX_ITEMS;
        }

        return totalUnits;
    }

    String getOrderId() {
        return orderId;
    }
}
~~~

Trong ví dụ:

- **orderId** và **itemCount** là instance field **final**, được khởi tạo trong constructor.
- **MAX_ITEMS** là field **static final** dùng chung cho lớp.
- **orderId** và **itemCount** trong constructor là tham số; **this.orderId** và **this.itemCount** chỉ field.
- **baseUnits** là biến cục bộ **final**, được gán một lần.
- **totalUnits** là biến cục bộ có thể được gán lại khi cần giới hạn số lượng.
- **excess** chỉ có phạm vi trong block **if** và không thể được sử dụng sau khi block kết thúc.

Khi đọc hoặc viết mã Java, hãy xác định biến thuộc loại nào, tên của nó có phạm vi ở đâu, nó được khởi tạo khi nào và có được phép gán lại hay không. Với **final**, kiểm tra cả thời điểm gán ban đầu và mọi đường đi có thể gán biến để bảo đảm chương trình tuân thủ quy tắc của trình biên dịch Java 27.
