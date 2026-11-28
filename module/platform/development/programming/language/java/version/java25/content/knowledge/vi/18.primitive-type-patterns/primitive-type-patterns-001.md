# Phạm vi preview lần thứ ba của primitive types in patterns, instanceof và switch

## 1. Định vị tính năng trước khi viết mã

Java 25 đưa **Primitive Types in Patterns, instanceof, and switch** vào lần preview thứ ba theo **JEP 507**. Tính năng mở rộng pattern matching để làm việc với các kiểu nguyên thủy như **byte**, **short**, **char**, **int**, **long**, **float**, **double** và **boolean**. Nó cho phép kiểm tra một phép chuyển đổi số có an toàn hay không, dùng primitive type pattern ở cấp cao nhất hoặc bên trong record pattern, và dùng primitive selector trong **switch**.

Tuy nhiên, đây chưa bao giờ là tính năng ngôn ngữ ổn định. Tại thời điểm JDK 25, nó vẫn yêu cầu bật preview khi biên dịch và chạy. Trạng thái hiện tại còn cần được đọc cẩn thận hơn: sau các lần preview tiếp theo trong JDK 26 và JDK 27, nhóm Java thông báo ngày **11/11/2026** rằng sẽ ngừng phát triển tính năng này, rút JEP preview tiếp theo và loại bỏ nó khỏi JDK 28. Vì vậy, bài này giải thích đúng phạm vi JDK 25 để người học hiểu JEP 507 và nhận diện mã đã thử nghiệm, đồng thời hướng dẫn cách giữ mã ứng dụng tương thích với Java ổn định.

Bài **Phạm vi preview lần thứ ba của primitive types in patterns, instanceof và switch** thuộc chương **Mẫu kiểu nguyên thủy** của module **JAVA_VERSION_JAVA25**. Nội dung gắn với định hướng học Java 25 hiện đại, nhưng không trình bày preview này như một kỹ thuật nên đưa vào dự án mới.

> **Trạng thái cần nhớ tại ngày 27/11/2026**
>
> - JDK 25: JEP 507 — Third Preview.
> - JDK 26: JEP 530 — Fourth Preview.
> - JDK 27: JEP 532 — Fifth Preview.
> - Ngày 11/11/2026: nhóm Java quyết định ngừng phát triển; JEP thứ sáu dự kiến bị rút và tính năng được lên kế hoạch loại bỏ khỏi JDK 28.
>
> Primitive type patterns không trở thành một phần ổn định của Java SE. Chỉ dùng các ví dụ preview để đọc hiểu, thử nghiệm có kiểm soát hoặc lập kế hoạch thay thế mã đã tồn tại.

### Sau bài này, bạn có thể

1. Phân biệt pattern matching với primitive types và các tính năng pattern matching đã ổn định cho reference types.
2. Mô tả phạm vi JEP 507 trong JDK 25 và vòng đời preview của tính năng.
3. Hiểu cách primitive type pattern kiểm tra phép chuyển đổi có bảo toàn giá trị hay không.
4. Phân biệt **instanceof** dùng để kiểm tra kiểu với **instanceof** dùng để khớp pattern và tạo pattern variable.
5. Đọc primitive patterns bên trong record patterns.
6. Hiểu primitive selector, primitive case patterns, **when** guard, tính exhaustive và pattern dominance trong **switch**.
7. Biên dịch/chạy ví dụ JDK 25 preview đúng cặp compiler/runtime.
8. Nhận diện mã phụ thuộc preview và thay bằng cách viết ổn định.
9. Hiểu vì sao không nên bắt đầu dự án mới dựa vào một preview đã có quyết định ngừng phát triển.

## 2. Lịch sử và trạng thái theo từng JDK

| JDK | JEP | Trạng thái |
| --- | --- | --- |
| 23 | JEP 455 | Preview lần đầu |
| 24 | JEP 488 | Preview lần thứ hai |
| 25 | JEP 507 | Preview lần thứ ba |
| 26 | JEP 530 | Preview lần thứ tư |
| 27 | JEP 532 | Preview lần thứ năm |
| 28 | JEP thứ sáu dự kiến | Đã thông báo rút đề xuất preview và lên kế hoạch loại bỏ tính năng |

JEP 507 trong JDK 25 không có thay đổi lớn so với lần preview thứ hai. Phạm vi chính vẫn là:

- Cho phép primitive type pattern trong các ngữ cảnh pattern.
- Mở rộng **instanceof** để kiểm tra khả năng chuyển đổi giữa primitive types và giữa các kiểu phù hợp khác.
- Cho phép primitive patterns trong record patterns.
- Mở rộng **switch** để làm việc với primitive selector và primitive patterns.
- Sử dụng kiểm tra chuyển đổi chính xác để tránh trường hợp pattern âm thầm làm mất dữ liệu.

Quyết định ngừng phát triển năm 2026 không làm cho kiến thức lịch sử của JEP 507 trở nên vô nghĩa. Nó thay đổi cách nên sử dụng kiến thức: hiểu cú pháp, đọc mã preview cũ và lập kế hoạch migration là hữu ích; coi tính năng như một nền tảng ổn định cho code mới thì không phù hợp.

### 2.1. Preview có nghĩa gì?

Preview feature là tính năng đã có thiết kế, đặc tả và implementation đủ để người dùng thử nghiệm, nhưng chưa được cam kết là một phần lâu dài của ngôn ngữ. Qua các lần preview, thiết kế có thể thay đổi, tiếp tục preview hoặc bị rút lại.

Một preview feature:

- Bị tắt mặc định.
- Cần cờ **--enable-preview** khi biên dịch và chạy.
- Gắn với một phiên bản JDK cụ thể.
- Có thể thay đổi hoặc bị loại bỏ ở release sau.
- Không nên được dùng như một API/ngôn ngữ ổn định mà thư viện công khai cam kết hỗ trợ dài hạn.

Việc một tính năng xuất hiện qua nhiều lần preview không tự động làm nó trở thành final.

### 2.2. Phân biệt preview này với pattern matching đã ổn định

Java đã có các tính năng pattern matching ổn định cho reference types:

| Tính năng | Trạng thái ổn định |
| --- | --- |
| Pattern matching với **instanceof** cho reference types | Final từ JDK 16 |
| Pattern matching với **switch** cho reference types | Final từ JDK 21 |
| Record patterns cho record reference types | Final từ JDK 21 |
| Primitive types trong type patterns, **instanceof**, record patterns và **switch** | Preview ở JDK 25; sau đó ngừng phát triển và dự kiến bị loại bỏ ở JDK 28 |

Do đó, quyết định rút primitive patterns không đồng nghĩa Java loại bỏ pattern matching nói chung. Các pattern với **String**, class, interface, enum và record reference types vẫn là phần ổn định của ngôn ngữ.

## 3. Vấn đề mà primitive type patterns muốn giải quyết

Pattern matching với reference types thường kiểm tra một giá trị có thể được xem như một kiểu cụ thể hay không, rồi tạo biến pattern đã có kiểu phù hợp.

~~~java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
~~~

Với primitive values, Java truyền thống yêu cầu người viết tự cast và tự kiểm tra range/precision. Ví dụ:

~~~java
int value = 127;
byte narrowed = (byte) value;
~~~

Phép cast từ **int** sang **byte** có thể làm mất thông tin nếu giá trị nằm ngoài khoảng **-128..127**. Một phép cast số nguyên hẹp hơn vẫn trả về kết quả, kể cả khi các bit cao bị loại bỏ.

Primitive type patterns được đề xuất để biểu diễn phép kiểm tra và chuyển đổi theo kiểu pattern matching:

~~~java
int value = 127;

if (value instanceof byte small) {
    System.out.println("Có thể biểu diễn chính xác bằng byte: " + small);
}
~~~

Nếu giá trị không thể chuyển đổi chính xác sang **byte**, pattern không khớp. Người viết không phải cast trước rồi kiểm tra lại kết quả.

Mục tiêu của thiết kế là kết hợp kiểm tra kiểu, kiểm tra khả năng chuyển đổi và khai báo biến nhận kết quả trong một cấu trúc có thể đọc được. Tuy nhiên, do tính năng đã bị rút khỏi lộ trình phát triển, cách viết này chỉ có ý nghĩa trong mã thử nghiệm JDK 25 hoặc khi đọc một codebase preview cũ.

## 4. Các khái niệm chuyển đổi cần hiểu trước

Primitive patterns dựa trên **testing conversion**: một phép chuyển đổi được kiểm tra tại runtime để xác định nó có thực hiện được và có bảo toàn thông tin hay không.

Không được đồng nhất ba khái niệm sau:

| Khái niệm | Ý nghĩa |
| --- | --- |
| Widening conversion | Chuyển sang kiểu có miền biểu diễn rộng hơn theo quy tắc Java |
| Narrowing conversion | Chuyển sang kiểu có miền biểu diễn hẹp hơn, có thể mất range hoặc precision |
| Exact testing conversion | Phép chuyển đổi cụ thể của giá trị hiện tại không làm mất thông tin |

Một phép widening không phải lúc nào cũng chính xác. Ví dụ, **int** sang **float** là widening nhưng **float** không thể biểu diễn chính xác mọi giá trị **int**. Ngược lại, **float** sang **double** là widening và luôn bảo toàn chính xác giá trị float đang được lưu.

### 4.1. Exactness phụ thuộc giá trị

Ví dụ chuyển **int** sang **byte**:

- **127** có thể biểu diễn chính xác bằng **byte**.
- **-128** có thể biểu diễn chính xác bằng **byte**.
- **128** không thể biểu diễn bằng **byte**.
- **-129** không thể biểu diễn bằng **byte**.

Ví dụ chuyển **float** sang **int**:

- **12.0f** có thể chuyển thành **12** mà không mất thông tin số học.
- **12.5f** không thể chuyển thành **int** mà vẫn giữ phần thập phân.
- **Float.NaN** và vô cực không thể chuyển thành giá trị **int** tương đương.
- Giá trị ngoài miền **int** không thể được biểu diễn chính xác bằng **int**.

Do đó, việc một kiểu đích rộng hay hẹp hơn chưa đủ để kết luận pattern sẽ khớp. Runtime phải kiểm tra giá trị thực tế.

### 4.2. Floating-point và giá trị đã được làm tròn

Ví dụ:

~~~java
float value = 1000.01f;

if (value instanceof double converted) {
    System.out.println(converted);
}
~~~

Pattern **double** khớp vì mọi giá trị **float** có thể được biểu diễn chính xác dưới dạng **double**.

Giá trị in ra có thể là **1000.010009765625** thay vì **1000.01**. Điều đó không có nghĩa phép chuyển **float** sang **double** bị mất thông tin. Giá trị **float** ban đầu đã là một xấp xỉ nhị phân của số thập phân **1000.01**; phép chuyển sang **double** bảo toàn chính xác giá trị nhị phân đó.

## 5. Primitive type patterns ở cấp cao nhất

Primitive type pattern có thể khai báo biến pattern mang kiểu nguyên thủy.

Ví dụ từ phạm vi JDK 25:

~~~java
float value = 1000.01f;

if (value instanceof float f) {
    System.out.println("float value: " + f);
}

if (value instanceof double d) {
    System.out.println("double value: " + d);
}

if (value instanceof int i) {
    System.out.println("int value: " + i);
}
~~~

Hai pattern đầu khớp:

- **float f** nhận giá trị cùng kiểu.
- **double d** nhận giá trị được widening chính xác từ **float**.

Pattern **int i** không khớp vì **1000.01f** không thể chuyển thành số nguyên **int** mà không mất phần thập phân.

### 5.1. Pattern variable chỉ tồn tại khi pattern khớp

~~~java
static void inspect(float value) {
    if (value instanceof double converted) {
        // converted chỉ được dùng trong phạm vi hợp lệ của nhánh này.
        System.out.println(converted);
    }
}
~~~

Biến **converted** được khởi tạo bởi thao tác pattern matching. Không có biến nhận kết quả để sử dụng nếu phép kiểm tra thất bại.

Quy tắc scope và definite assignment vẫn quan trọng như với pattern variable của reference types. Không được dùng biến pattern ở một nhánh điều khiển mà pattern có thể chưa khớp.

### 5.2. instanceof dạng type comparison và dạng pattern matching

Trong preview, **instanceof** có hai cách dùng khác nhau:

**Type comparison** chỉ kiểm tra:

~~~java
int value = 127;

if (value instanceof byte) {
    // Chỉ xác nhận chuyển đổi sang byte là chính xác.
    // value vẫn có kiểu int.
    System.out.println((byte) value);
}
~~~

**Pattern matching** kiểm tra và tạo biến đã chuyển đổi:

~~~java
int value = 127;

if (value instanceof byte small) {
    // small có kiểu byte.
    System.out.println(small);
}
~~~

Type comparison không tự chuyển kiểu biến gốc. Pattern matching có biến pattern để sử dụng giá trị ở kiểu đích khi phép chuyển đổi chính xác.

## 6. Kiểm tra phép cast an toàn bằng instanceof

Một ứng dụng thường nhận giá trị số từ nhiều nguồn: dữ liệu cấu hình, JSON, kết quả tính toán, API bên ngoài hoặc một thuật toán có kiểu tổng quát. Khi cần chuyển giá trị sang kiểu nguyên thủy nhỏ hơn, việc kiểm tra trước khi cast giúp tránh mất thông tin.

Ví dụ kiểm tra **int** có thể chuyển thành **byte**:

~~~java
static void printIfByte(int value) {
    if (value instanceof byte b) {
        System.out.println("Giá trị byte: " + b);
    } else {
        System.out.println("Không thể biểu diễn chính xác bằng byte");
    }
}
~~~

Kết quả:

| Đầu vào | Pattern **byte b** |
| ---: | --- |
| **127** | Khớp |
| **-128** | Khớp |
| **128** | Không khớp |
| **-129** | Không khớp |

Với cách viết truyền thống, lập trình viên phải tự kiểm tra biên:

~~~java
static void printIfByteStable(int value) {
    if (value >= Byte.MIN_VALUE && value <= Byte.MAX_VALUE) {
        byte b = (byte) value;
        System.out.println("Giá trị byte: " + b);
    }
}
~~~

Ví dụ thứ hai là cách có thể dùng trong Java ổn định hiện nay. Nó không phụ thuộc primitive pattern preview.

### 6.1. Kiểm tra float có thể chuyển thành int

Primitive pattern preview có thể biểu diễn phép kiểm tra chuyển đổi từ floating-point sang integral type. Đây là nơi cần chú ý precision, phần thập phân, NaN, infinity và giới hạn miền biểu diễn.

Ví dụ minh họa ý nghĩa:

~~~java
static void inspectFloat(float value) {
    if (value instanceof int exact) {
        System.out.println("Giá trị int chính xác: " + exact);
    } else {
        System.out.println("Chuyển đổi sang int sẽ làm mất thông tin");
    }
}
~~~

Một vài trường hợp:

| Giá trị | Chuyển thành **int** có chính xác không? |
| --- | --- |
| **12.0f** | Có |
| **12.5f** | Không |
| **-12.0f** | Có |
| **Float.NaN** | Không |
| **Float.POSITIVE_INFINITY** | Không |
| Giá trị vượt miền **int** | Không |

Không nên nhầm kết quả của phép cast Java thông thường với kiểm tra exactness. Cast từ **float** sang **int** có thể cắt phần thập phân hoặc bão hòa tại giới hạn số nguyên; primitive pattern được thiết kế để không coi một chuyển đổi mất thông tin là match thành công.

## 7. Primitive patterns bên trong record patterns

Record pattern cho phép kiểm tra một record và phân rã các component. JEP 507 mở rộng khả năng để component pattern có kiểu nguyên thủy, kể cả khi component của record có kiểu primitive khác.

Ví dụ:

~~~java
record Cup(double volume) { }

Cup cup = new Cup(34.567f);

if (cup instanceof Cup(double d)) {
    System.out.println("double: " + d);
}

if (cup instanceof Cup(float f)) {
    System.out.println("float: " + f);
}

if (cup instanceof Cup(int i)) {
    System.out.println("int: " + i);
}
~~~

**Cup** lưu component **double**. Giá trị truyền vào được tạo từ một **float**, sau đó widening sang **double**. Vì vậy:

- **Cup(double d)** khớp.
- **Cup(float f)** có thể khớp nếu giá trị double chuyển ngược về float mà không mất thông tin.
- **Cup(int i)** không khớp với giá trị có phần thập phân.

Record pattern kết hợp hai bước: xác định đối tượng là record phù hợp và kiểm tra từng component theo pattern tương ứng.

### 7.1. Dùng var trong component pattern

Record patterns còn hỗ trợ suy luận kiểu cho component pattern:

~~~java
record Measurement(double value, String unit) { }

static void printMeasurement(Object input) {
    if (input instanceof Measurement(var value, var unit)) {
        System.out.println(value + " " + unit);
    }
}
~~~

Ví dụ này dùng **var** để suy luận kiểu component. **var** ở đây không phải primitive type pattern cụ thể. Nếu muốn yêu cầu chuyển đổi component sang một primitive type khác, cú pháp primitive pattern sẽ được dùng; phần mở rộng đó thuộc preview đang được nói tới.

### 7.2. Khi nào record pattern hữu ích?

Trong JDK 25 preview, primitive record patterns có thể giúp kiểm tra và lấy component ở kiểu số mong muốn mà không phải viết các bước cast riêng. Ví dụ, một record lưu **double** nhưng consumer muốn nhận **float** khi phép chuyển đổi không mất thông tin.

Với mã ứng dụng hiện nay, hãy ưu tiên record patterns ổn định cho component reference types hoặc đọc component bằng accessor rồi thực hiện kiểm tra/cast rõ ràng theo quy tắc nghiệp vụ.

## 8. Primitive selector và case pattern trong switch

JEP 507 mở rộng **switch** để selector có thể là primitive type và cho phép dùng primitive type patterns trong **case**.

Ví dụ selector **double**:

~~~java
static String doubleToRating(double rating) {
    return switch (rating) {
        case 0d -> "0 stars";
        case double d when d > 0d && d < 2.5d
            -> d + " is not good";
        case double d when d >= 2.5d && d < 5d
            -> d + " is better";
        case 5d -> "5 stars";
        default -> "Invalid rating";
    };
}
~~~

Ví dụ dùng primitive selector **long**:

~~~java
static void describe(long value) {
    switch (value) {
        case long n when n < 1_000_000L ->
            System.out.println("Less than a million");
        case long n when n < 1_000_000_000L ->
            System.out.println("Less than a billion");
        case long n when n < 1_000_000_000_000L ->
            System.out.println("Less than a trillion");
        default ->
            System.out.println("At least a trillion");
    }
}
~~~

Các ví dụ này minh họa phạm vi preview của JDK 25. Chúng không phải cú pháp ổn định để đưa vào code mới sau quyết định ngừng phát triển primitive patterns.

### 8.1. Case constant phải khớp kiểu selector

Khi dùng case constant cho các primitive selector, kiểu của constant phải theo quy tắc của selector.

Ví dụ:

~~~java
static String classify(long value) {
    return switch (value) {
        case 5L -> "five";
        case 10L -> "ten";
        default -> "other";
    };
}
~~~

Với selector **float**, dùng literal **float** như **5f**; với selector **double**, dùng literal **double** như **5d**. Không tùy tiện trộn literal số nguyên với selector floating-point vì một phép widening có thể làm mất độ chính xác.

### 8.2. Primitive pattern có thể kiểm tra conversion

Một **case** pattern có thể kiểm tra selector có chuyển đổi chính xác sang kiểu pattern hay không. Ví dụ, một selector **float** có thể khớp **double** vì widening **float** sang **double** luôn chính xác.

~~~java
static double asDouble(float value) {
    return switch (value) {
        case double d -> d;
    };
}
~~~

Một pattern **int** không thể bao phủ mọi giá trị **float**, vì có giá trị có phần thập phân, vô cực hoặc nằm ngoài miền **int**. Vì vậy, nếu switch expression không có nhánh xử lý các giá trị còn lại, compiler có thể báo không exhaustive.

## 9. when guard và pattern variable

**when** guard là biểu thức boolean bổ sung điều kiện cho một pattern. Guard được đánh giá sau khi pattern đã khớp; pattern variable có thể được dùng trong guard và nhánh xử lý.

~~~java
static String classify(double value) {
    return switch (value) {
        case double d when d < 0d -> "negative";
        case double d when d == 0d -> "zero";
        case double d when d > 0d -> "positive";
        default -> "not classified";
    };
}
~~~

Các nhánh trên minh họa cách dùng primitive pattern với guard. Trong một chương trình thật, cần xử lý đầy đủ các giá trị đặc biệt của floating-point như NaN và vô cực nếu chúng có thể xuất hiện. Không giả định ba điều kiện trên tự động phân loại mọi giá trị **double**.

### 9.1. Guard không biến pattern thành phép cast

Guard chỉ chạy sau khi pattern match thành công. Nó không sửa một phép chuyển đổi không an toàn thành chuyển đổi an toàn.

~~~java
float value = 12.5f;

switch (value) {
    case int i when i > 0 ->
        System.out.println(i);
    default ->
        System.out.println("Không thể chuyển chính xác sang int");
}
~~~

Trong ví dụ, guard không được dùng để chấp nhận **12.5f** rồi cắt thành **12**. Pattern **int i** phải khớp trước; do phần thập phân bị mất, pattern không khớp và nhánh guard không chạy.

## 10. Exhaustiveness và pattern dominance

Một **switch** expression phải xử lý mọi giá trị có thể xuất hiện theo quy tắc exhaustive switch. Enhanced **switch** statement cũng có yêu cầu exhaustiveness trong các trường hợp được quy định.

Nếu một primitive selector có thể chứa giá trị không được pattern bao phủ, cần thêm **default** hoặc pattern phù hợp.

Ví dụ một pattern **int** không bao phủ mọi giá trị **float**:

~~~java
static String inspect(float value) {
    return switch (value) {
        case int i -> "int: " + i;
        // Không đủ để bao phủ mọi float.
        default -> "not an exact int";
    };
}
~~~

### 10.1. Pattern rộng có thể dominate pattern hẹp

Pattern được gọi là dominate khi mọi giá trị khớp pattern phía sau cũng đã khớp pattern trước đó.

Ví dụ về ý tưởng:

- Nếu một pattern nhận mọi giá trị **int**, pattern đó có thể bao phủ các giá trị **byte** vì mọi **byte** chuyển sang **int** chính xác.
- Nếu pattern rộng đứng trước pattern hẹp, nhánh hẹp có thể không bao giờ được chọn.
- Compiler kiểm tra dominance và từ chối một số thứ tự case không hợp lệ.

Với preview JDK 25, cần đọc lỗi compiler khi sắp xếp primitive patterns. Không dựa vào thứ tự case như một phép thử tuần tự không có quy tắc; compiler phân tích miền giá trị và khả năng chuyển đổi.

### 10.2. Wrapper type và null

Wrapper types như **Integer**, **Double** và **Boolean** là reference types. Chúng có thể chứa **null**, trong khi primitive values không có giá trị null.

Khi pattern hoặc testing conversion cần unboxing, phải hiểu rằng dữ liệu wrapper có thể null. Không giả định một wrapper null tương đương primitive zero hoặc false. Với dữ liệu đầu vào có thể null, kiểm tra null rõ ràng trước khi chuyển đổi hoặc dùng pattern/reference branch thích hợp.

## 11. Phân biệt pattern preview với cú pháp switch ổn định

Không phải mọi **switch** hay mọi pattern đều phụ thuộc JEP 507.

| Cú pháp | Trạng thái |
| --- | --- |
| **switch (intValue)** với **case 1**, **case 2** | Ổn định |
| **switch (enumValue)** | Ổn định |
| **switch (referenceValue)** với type pattern **case String s** | Ổn định |
| **instanceof String s** | Ổn định |
| Record pattern trên reference component thông thường | Ổn định |
| **switch (doubleValue)** | Primitive patterns preview trong phạm vi JDK 25 |
| **if (floatValue instanceof double d)** | Primitive type pattern preview |
| **record instanceof Record(int component)** khi component primitive pattern khác kiểu lưu | Primitive record pattern preview |

Điểm phân biệt không phải “pattern matching có phải preview không”. Pattern matching cho reference types đã final từ các JDK trước. Preview đang xét là việc đưa primitive values và primitive conversions vào các ngữ cảnh pattern.

## 12. Bật preview trong JDK 25 để đọc/thử ví dụ

Chỉ thực hiện trong môi trường học tập hoặc thử nghiệm tương thích với JDK 25.

Biên dịch:

~~~bash
javac --enable-preview --release 25 PrimitivePatternDemo.java
~~~

Chạy bằng đúng JDK 25:

~~~bash
java --enable-preview PrimitivePatternDemo
~~~

Các lưu ý:

1. Dùng compiler của JDK 25 để biên dịch source release 25.
2. Bật **--enable-preview** ở cả compiler và runtime.
3. Preview feature bị tắt mặc định.
4. Class file dùng preview feature gắn với release đã biên dịch.
5. Không giả định class file preview của JDK 25 sẽ chạy được trên JDK mới hơn.
6. Không đưa flag này vào toàn bộ build production chỉ để thử một ví dụ.
7. Không dùng **--enable-preview** như cách bật một tính năng đã bị rút hoặc bị loại bỏ ở release sau.

Oracle JDK 25 mô tả rõ quy trình biên dịch preview với **--enable-preview** cùng **--release 25**, và chạy bằng **java --enable-preview**. Cần dùng cùng release vì preview feature không có cam kết tương thích giữa các phiên bản.

### 12.1. Kiểm tra compiler/runtime

~~~bash
java -version
javac -version
~~~

Hai công cụ phải thuộc JDK 25 cho ví dụ của bài. Nếu máy có nhiều JDK, gọi binary qua đường dẫn cài đặt cụ thể để tránh **java** và **javac** trỏ tới hai phiên bản khác nhau.

### 12.2. Không dùng preview trong thư viện public

Một thư viện được phát hành cho nhiều ứng dụng cần có contract ổn định. Nếu public API hoặc bytecode của thư viện phụ thuộc preview:

- Người dùng phải bật preview tương ứng.
- Khả năng tương thích giữa các JDK release bị giới hạn.
- Nâng cấp runtime có thể yêu cầu sửa source.
- Feature có thể bị thay đổi hoặc bị loại bỏ.

Với tình trạng đã công bố ngừng phát triển, không nên thêm dependency mới vào preview này.

## 13. Ví dụ tổng hợp cho JDK 25 preview

Ví dụ dưới đây gom primitive type pattern, safe conversion, record pattern và switch pattern vào một file. Đây là mã minh họa lịch sử cho JDK 25 preview, không phải mã khuyến nghị cho dự án mới.

~~~java
record Reading(double value, String unit) { }

public class PrimitivePatternDemo {

    static void inspectNumber(float value) {
        if (value instanceof float f) {
            System.out.println("float: " + f);
        }

        if (value instanceof double d) {
            System.out.println("double: " + d);
        }

        if (value instanceof int i) {
            System.out.println("exact int: " + i);
        } else {
            System.out.println("not an exact int");
        }
    }

    static void inspectReading(Reading reading) {
        if (reading instanceof Reading(double d, String unit)) {
            System.out.println("reading: " + d + " " + unit);
        }

        if (reading instanceof Reading(float f, String unit)) {
            System.out.println("exact float: " + f + " " + unit);
        }
    }

    static String rate(double value) {
        return switch (value) {
            case 0d -> "zero";
            case double d when d > 0d && d < 2.5d -> "low";
            case double d when d >= 2.5d && d < 5d -> "medium";
            case 5d -> "maximum";
            default -> "outside supported range";
        };
    }

    public static void main(String[] args) {
        inspectNumber(1000.01f);
        inspectNumber(12.0f);

        inspectReading(new Reading(34.5d, "ml"));
        inspectReading(new Reading(34.0d, "ml"));

        System.out.println(rate(4.5d));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --enable-preview --release 25 PrimitivePatternDemo.java
java --enable-preview PrimitivePatternDemo
~~~

Khi thử nghiệm, hãy quan sát trường hợp pattern không khớp. Đặc biệt, **1000.01f** không phải một số nguyên chính xác, trong khi **12.0f** có thể được chuyển sang **int** mà không mất thông tin.

## 14. Cách viết ổn định thay thế primitive type patterns

Vì tính năng đã có quyết định ngừng phát triển và dự kiến loại bỏ khỏi JDK 28, mã ứng dụng nên biểu diễn việc kiểm tra range/precision một cách tường minh.

### 14.1. Chuyển int sang byte an toàn

~~~java
import java.util.Optional;

static Optional<Byte> toByte(int value) {
    if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
        return Optional.empty();
    }

    return Optional.of((byte) value);
}
~~~

Cách này dùng Java ổn định. Phép cast chỉ xảy ra sau khi giá trị đã được kiểm tra nằm trong miền biểu diễn của **byte**.

### 14.2. Chuyển double sang int khi không mất thông tin

~~~java
import java.util.OptionalInt;

static OptionalInt toExactInt(double value) {
    if (!Double.isFinite(value)) {
        return OptionalInt.empty();
    }

    if (value < Integer.MIN_VALUE || value > Integer.MAX_VALUE) {
        return OptionalInt.empty();
    }

    if (value != Math.rint(value)) {
        return OptionalInt.empty();
    }

    return OptionalInt.of((int) value);
}
~~~

Cách này kiểm tra:

- Giá trị là hữu hạn.
- Giá trị nằm trong miền **int**.
- Giá trị không có phần lẻ.
- Chỉ sau khi kiểm tra mới thực hiện cast.

Nếu nghiệp vụ có quy tắc làm tròn, hãy dùng **Math.round**, **Math.floor** hoặc **Math.ceil** theo chủ đích. Không dùng cast như một cách làm tròn ngầm.

### 14.3. Dùng pattern matching ổn định cho wrapper/reference types

Nếu dữ liệu thực sự là object wrapper, pattern matching reference type vẫn ổn định:

~~~java
static void inspectObject(Object value) {
    if (value instanceof Integer integer) {
        System.out.println("Integer object: " + integer);
    } else if (value instanceof Double decimal) {
        System.out.println("Double object: " + decimal);
    } else {
        System.out.println("Other reference value");
    }
}
~~~

Cách này kiểm tra kiểu object thực tế. Nó không tương đương với việc kiểm tra một primitive value có thể chuyển chính xác sang kiểu số khác, nhưng phù hợp khi dữ liệu đầu vào là wrapper objects.

### 14.4. Dùng if/else cho primitive selector

Nếu cần phân loại **double**, dùng các điều kiện có chủ đích:

~~~java
static String stableRating(double rating) {
    if (!Double.isFinite(rating)) {
        return "invalid";
    }

    if (rating == 0d) {
        return "zero";
    }

    if (rating > 0d && rating < 2.5d) {
        return "low";
    }

    if (rating >= 2.5d && rating < 5d) {
        return "medium";
    }

    if (rating == 5d) {
        return "maximum";
    }

    return "outside supported range";
}
~~~

Điều kiện tường minh có thể dài hơn switch pattern, nhưng chạy trên Java ổn định và thể hiện rõ chính sách đối với NaN, infinity và miền giá trị.

## 15. Rủi ro khi dùng primitive patterns trong mã ứng dụng

### 15.1. Phụ thuộc compiler và runtime cùng release

Một class đã biên dịch với preview feature không có cam kết chạy trên release khác. Điều này làm tăng chi phí build, test, đóng gói và triển khai.

### 15.2. Hành vi chuyển đổi số khó nhìn thấy

Primitive pattern có thể thực hiện conversion khi match thành công. Nếu người đọc không hiểu exactness, họ có thể nhầm rằng pattern là một phép so sánh kiểu đơn giản.

### 15.3. Floating-point có quy tắc đặc biệt

NaN, infinity, positive zero, negative zero, độ chính xác nhị phân và miền biểu diễn có thể làm kết quả match khác trực giác. Với code nghiệp vụ, nên thể hiện rõ quy tắc số học.

### 15.4. Pattern dominance có thể làm case không hợp lệ

Một pattern rộng có thể bao phủ pattern hẹp. Compiler có thể từ chối switch block vì nhánh phía sau không thể được chọn. Khi chuyển đổi số, việc kiểm tra dominance phụ thuộc quan hệ exactness.

### 15.5. Quyết định rút tính năng làm tăng chi phí migration

Đến ngày 11/11/2026, nhóm Java đã thông báo ngừng phát triển. JDK 28 được lên kế hoạch loại bỏ tính năng. Dự án đang dùng mã preview cần có kế hoạch thay thế trước khi nâng cấp runtime.

## 16. Quy trình nhận diện và migration mã preview

Nếu một codebase đã thử primitive type patterns trong JDK 25/26/27, thực hiện theo các bước:

1. Tìm các biểu thức **instanceof** có kiểu nguyên thủy ở vế phải.
2. Tìm **case** labels khai báo primitive type pattern.
3. Tìm record patterns có component pattern primitive.
4. Xác định phép chuyển đổi mong muốn: range check, exact conversion hay làm tròn.
5. Viết lại bằng kiểm tra range/precision tường minh hoặc wrapper/reference pattern phù hợp.
6. Bổ sung test cho biên dưới, biên trên, phần lẻ, NaN, infinity và null wrapper nếu có.
7. Biên dịch bằng JDK đích không bật preview.
8. Chạy test trên runtime dự kiến nâng cấp.
9. Xóa **--enable-preview** nếu không còn preview feature nào khác cần dùng.

Không thay mọi primitive pattern bằng một phép cast trực tiếp. Cast có thể làm mất thông tin; cần giữ lại điều kiện kiểm tra mà pattern cũ đã thực hiện.

## 17. Bài tập thực hành có kiểm soát

Các bài tập sau chỉ dành cho môi trường JDK 25 preview để hiểu JEP 507 và đọc mã cũ. Không dùng kết quả như quyết định chọn tính năng cho một dự án mới.

### Bài tập A — kiểm tra widening chính xác

Khai báo một biến **float**, kiểm tra pattern **float** và **double**, rồi giải thích vì sao pattern **double** khớp.

**Đạt khi:** phân biệt được giá trị float đang lưu với số thập phân ban đầu.

### Bài tập B — kiểm tra narrowing có mất thông tin

Dùng các giá trị **127**, **128**, **-128**, **-129** để kiểm tra khả năng chuyển từ **int** sang **byte**.

**Đạt khi:** giải thích được vì sao chỉ các giá trị trong miền biểu diễn mới khớp.

### Bài tập C — kiểm tra floating-point

Thử **12.0f**, **12.5f**, **Float.NaN** và **Float.POSITIVE_INFINITY** với pattern **int**.

**Đạt khi:** nhận biết pattern yêu cầu phép chuyển đổi không mất thông tin, không chỉ yêu cầu phép cast có thể chạy.

### Bài tập D — record pattern

Tạo record có component **double**, sau đó thử pattern component **double**, **float** và **int**.

**Đạt khi:** giải thích được việc pattern kiểm tra chuyển đổi của component.

### Bài tập E — switch primitive selector

Thử **switch** với selector **double** và **long**, kết hợp **case** constants, primitive type patterns và **when** guards.

**Đạt khi:** giải thích được vai trò của guard, exhaustiveness và pattern dominance.

### Bài tập F — viết lại không dùng preview

Chuyển các ví dụ **instanceof int**, **instanceof byte** và **switch(double)** thành Java ổn định bằng kiểm tra range, precision và **if/else**.

**Đạt khi:** code biên dịch mà không cần **--enable-preview**, đồng thời giữ nguyên quy tắc không làm mất dữ liệu.

## 18. Checklist đánh giá bài học

- [ ] Biết JEP 507 là lần preview thứ ba trong JDK 25.
- [ ] Không nhầm primitive type patterns với pattern matching reference types đã final.
- [ ] Hiểu testing conversion và exactness.
- [ ] Biết widening không phải lúc nào cũng exact.
- [ ] Phân biệt **instanceof** type comparison với pattern matching.
- [ ] Hiểu primitive patterns trong record patterns.
- [ ] Hiểu primitive selector và primitive case patterns trong switch.
- [ ] Biết **when** guard chỉ chạy sau khi pattern khớp.
- [ ] Hiểu exhaustiveness và pattern dominance.
- [ ] Biết cách bật preview khi thử trên đúng JDK 25.
- [ ] Biết preview không có cam kết tương thích giữa các release.
- [ ] Biết nhóm Java đã thông báo ngừng phát triển và dự kiến loại bỏ tính năng khỏi JDK 28.
- [ ] Không thêm primitive patterns vào code production mới.
- [ ] Biết thay bằng range check, exactness check hoặc reference patterns ổn định.
- [ ] Có test cho giá trị biên, phần lẻ, NaN, infinity và null wrapper khi phù hợp.

## 19. Tài liệu tham khảo chính thức

1. [JEP 507 — Primitive Types in Patterns, instanceof, and switch (Third Preview)](https://openjdk.org/jeps/507): phạm vi preview của JDK 25.
2. [Oracle Java SE 25 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html): xác nhận JEP 507 là preview lần thứ ba trong Java 25.
3. [Oracle Java SE 25 — Type Patterns](https://docs.oracle.com/en/java/javase/25/language/type-patterns.html): primitive type patterns và ví dụ instanceof.
4. [Oracle Java SE 25 — Record Patterns](https://docs.oracle.com/en/java/javase/25/language/record-patterns.html): primitive types trong record component patterns.
5. [Oracle Java SE 25 — Pattern Matching with switch](https://docs.oracle.com/en/java/javase/25/language/pattern-matching-switch.html): primitive selector, when guards và switch patterns.
6. [Oracle Java SE 25 — Safe Casting with instanceof and switch](https://docs.oracle.com/en/java/javase/25/language/safe-casting-instanceof-switch.html): exact conversion và kiểm tra cast an toàn.
7. [Oracle Java SE 25 — Preview Features](https://docs.oracle.com/en/java/javase/25/language/preview-language-vm-features.html): cách bật preview, giới hạn tương thích và vòng đời preview.
8. [Oracle Java SE 25 — Primitive Types in Patterns JLS Changes](https://docs.oracle.com/en/java/javase/25/docs/specs/primitive-types-in-patterns-instanceof-switch-jls.html): thay đổi đặc tả ngôn ngữ trong JDK 25.
9. [Oracle Java SE 26 — JEP 530, Fourth Preview](https://openjdk.org/jeps/530): lần preview tiếp theo và các thay đổi trong JDK 26.
10. [Oracle Java SE 27 — JEP 532, Fifth Preview](https://openjdk.org/jeps/532): lần preview thứ năm trong JDK 27.
11. [Inside Java — Withdrawing the Primitive Patterns Preview Feature (11/11/2026)](https://inside.java/2026/11/11/withdraw-primitive-patterns-preview/): thông báo ngừng phát triển, rút JEP thứ sáu dự kiến và kế hoạch loại bỏ khỏi JDK 28.

**Kết quả mong đợi:** người học hiểu được JEP 507 đã thử nghiệm điều gì trong JDK 25, biết đọc primitive type patterns và các quy tắc exact conversion, nhưng cũng nhận diện chính xác vòng đời của tính năng. Tại thời điểm hiện nay, primitive type patterns không phải nền tảng ổn định để phát triển mới; hãy dùng kiến thức này để hiểu mã preview và thay thế nó bằng kiểm tra chuyển đổi tường minh hoặc các pattern reference type đã ổn định.
