# Vòng lặp for, while, do-while và enhanced for

Vòng lặp cho phép chương trình thực hiện một nhóm câu lệnh nhiều lần. Thay vì viết lại cùng một thao tác cho từng lượt hoặc từng phần tử, bạn mô tả điều kiện tiếp tục và công việc cần lặp. Java 27 có các dạng vòng lặp **for**, **while**, **do-while** và **enhanced for**.

Đây đều là cú pháp chuẩn của Java, không cần bật preview feature. Mỗi dạng phù hợp với một tình huống: lặp theo số lần hoặc chỉ số, lặp đến khi trạng thái thay đổi, thực hiện ít nhất một lần, hoặc duyệt lần lượt các phần tử của mảng và đối tượng **Iterable**.

Các đoạn mã trong bài là phần thân của method, trừ ví dụ tổng hợp có khai báo **main** đầy đủ. Nếu đặt chúng trong một lớp thông thường, hãy thêm import cho các kiểu **java.util** được sử dụng, chẳng hạn **List**, **Map**, **Iterator**, **ArrayList** và **Arrays**. Trong compact source file của Java 27, các kiểu công khai được export bởi module **java.base** được import ngầm.

## 1. Cấu trúc chung của vòng lặp

Một vòng lặp thường có ba phần:

1. **Khởi tạo** trạng thái ban đầu, chẳng hạn biến đếm.
2. **Điều kiện** quyết định có thực hiện lượt tiếp theo hay không.
3. **Cập nhật** trạng thái để tiến gần đến điểm kết thúc.

Phần thân vòng lặp chứa công việc được thực hiện ở mỗi lượt. Nếu trạng thái không thay đổi theo cách khiến điều kiện trở thành **false**, vòng lặp có thể chạy mãi.

Ví dụ, in các số từ 1 đến 5:

~~~java
for (int number = 1; number <= 5; number++) {
    System.out.println(number);
}
~~~

Kết quả:

~~~text
1
2
3
4
5
~~~

Một vòng lặp có thể thực hiện không lần nào, một lần hoặc nhiều lần. Điểm khác nhau giữa các loại vòng lặp nằm ở vị trí kiểm tra điều kiện, cách cập nhật và cách lấy phần tử tiếp theo.

## 2. Vòng lặp for cơ bản

Dùng **for** cơ bản khi biết cách đếm lượt, cần chỉ số để truy cập phần tử, hoặc muốn đặt phần khởi tạo, điều kiện và cập nhật tại cùng một vị trí.

### 2.1. Cú pháp và thứ tự thực hiện

Cú pháp:

~~~java
for (khởi_tạo; điều_kiện; cập_nhật) {
    // thân vòng lặp
}
~~~

Biểu thức điều kiện của các vòng lặp có điều kiện phải có kiểu **boolean** hoặc **Boolean**. Nếu dùng **Boolean** mà giá trị là **null**, quá trình chuyển sang **boolean** sẽ gây **NullPointerException**; thông thường nên dùng biểu thức boolean nguyên thủy.

Ba phần trong dấu ngoặc có vai trò riêng:

| Phần | Thời điểm thực hiện | Mục đích |
|---|---|---|
| Khởi tạo | Một lần trước lượt đầu tiên | Khai báo hoặc gán giá trị ban đầu |
| Điều kiện | Trước mỗi lượt | Nếu **true**, chạy thân; nếu **false**, kết thúc |
| Cập nhật | Sau khi thân kết thúc bình thường hoặc gặp **continue** nhắm đến vòng **for** này | Tăng, giảm hoặc cập nhật trạng thái |

Thứ tự thực hiện:

~~~mermaid
flowchart TD
    A["Khởi tạo"] --> B["Đánh giá điều kiện"]
    B -->|true| C["Thực hiện thân vòng lặp"]
    C --> D["Cập nhật"]
    D --> B
    B -->|false| E["Thoát vòng lặp"]
~~~

Ví dụ đếm từ 0 đến 4:

~~~java
for (int i = 0; i < 5; i++) {
    System.out.println("Lượt " + i);
}
~~~

Ở đây, **int i = 0** chạy một lần khi bắt đầu; **i < 5** được kiểm tra trước mỗi lượt; **i++** chạy sau phần thân để tăng biến đếm lên 1. Khi **i** bằng 5, điều kiện sai và vòng lặp kết thúc.

Điều kiện được kiểm tra trước khi chạy thân, vì vậy nếu điều kiện sai ngay từ đầu thì thân vòng lặp không được thực hiện:

~~~java
for (int i = 10; i < 5; i++) {
    System.out.println(i); // Không được thực hiện
}
~~~

### 2.2. Đếm giảm và thay đổi bước

Phần cập nhật không bắt buộc phải dùng **i++**. Bạn có thể đếm lùi hoặc tăng theo bước phù hợp:

~~~java
for (int i = 5; i >= 1; i--) {
    System.out.println(i);
}
~~~

~~~java
for (int i = 0; i <= 10; i += 2) {
    System.out.println(i);
}
~~~

Ví dụ thứ nhất in từ 5 về 1. Ví dụ thứ hai chỉ in các số chẵn từ 0 đến 10. Hãy chọn điều kiện và bước cập nhật nhất quán để tránh bỏ sót hoặc lặp lại giá trị.

### 2.3. Các phần trong for có thể được lược bỏ

Cả phần khởi tạo, điều kiện và cập nhật đều có thể để trống, nhưng phải giữ hai dấu chấm phẩy phân cách:

~~~java
int i = 0;

for (; i < 3;) {
    System.out.println(i);
    i++;
}
~~~

Ví dụ này tương đương với một vòng lặp đếm thông thường. Khi không có lý do đặc biệt, nên đặt phần cập nhật trong đầu vòng lặp để người đọc dễ theo dõi.

Nếu bỏ phần điều kiện, Java xem điều kiện như luôn đúng:

~~~java
for (;;) {
    // Thực hiện công việc cho đến khi có lệnh thoát
}
~~~

Đây là vòng lặp vô hạn có chủ đích. Cần có đường thoát rõ ràng, thường là một lệnh **break** khi đạt điều kiện kết thúc.

### 2.4. Phạm vi biến đếm

Nếu biến đếm chỉ dùng trong vòng lặp, hãy khai báo ngay ở phần khởi tạo:

~~~java
for (int index = 0; index < 3; index++) {
    System.out.println(index);
}

// index không còn trong phạm vi sử dụng tại đây
~~~

Biến **index** chỉ có phạm vi trong câu lệnh **for** và thân vòng lặp. Cách khai báo này hạn chế việc vô tình dùng hoặc thay đổi biến đếm ở những đoạn mã khác.

Nếu cần dùng giá trị sau vòng lặp, khai báo biến trước vòng lặp:

~~~java
int index;

for (index = 0; index < 3; index++) {
    System.out.println(index);
}

System.out.println("Giá trị sau vòng lặp: " + index);
~~~

### 2.5. Nhiều biến khởi tạo hoặc cập nhật

Một vòng **for** có thể khởi tạo và cập nhật nhiều biểu thức, ngăn cách bằng dấu phẩy:

~~~java
for (int left = 0, right = 4; left < right; left++, right--) {
    System.out.println(left + " - " + right);
}
~~~

Cách này hữu ích khi hai biến tiến về nhau hoặc cần cập nhật song song. Các biến được khai báo trong cùng một khai báo biến phải có cùng kiểu tường minh. Không nên gom nhiều biến vào một vòng lặp nếu điều đó làm luồng xử lý khó đọc.

## 3. Vòng lặp while

Dùng **while** khi số lượt lặp chưa biết trước và việc tiếp tục phụ thuộc vào một điều kiện hoặc trạng thái thay đổi trong thân vòng lặp.

Cú pháp:

~~~java
while (điều_kiện) {
    // thân vòng lặp
}
~~~

Java đánh giá điều kiện trước mỗi lượt. Khi điều kiện là **true**, thân vòng lặp được thực hiện; khi điều kiện là **false**, chương trình thoát khỏi vòng lặp. Vì điều kiện được kiểm tra trước, thân vòng lặp có thể không chạy lần nào.

Ví dụ đếm đến khi biến đạt 5:

~~~java
int count = 1;

while (count <= 5) {
    System.out.println(count);
    count++;
}
~~~

Kết quả là các số từ 1 đến 5. Biến **count** được tăng trong thân vòng lặp; nếu quên cập nhật biến này, điều kiện vẫn đúng và chương trình có thể lặp vô hạn.

### 3.1. Lặp khi chưa biết số lần

Ví dụ đọc dữ liệu cho đến khi người dùng nhập lệnh dừng:

~~~java
String command = IO.readln("Nhập lệnh (exit để dừng): ");

while (command != null && !command.equalsIgnoreCase("exit")) {
    IO.println("Bạn vừa nhập: " + command);
    command = IO.readln("Nhập lệnh (exit để dừng): ");
}

IO.println("Đã kết thúc.");
~~~

Trong ví dụ này, số lần lặp phụ thuộc vào dữ liệu người dùng nhập. Điều kiện kiểm tra cả trường hợp luồng nhập kết thúc (**null**) để tránh gọi method trên một tham chiếu null.

**IO.readln** là API nhập/xuất theo dòng có trong Java 27. Trong chương trình dùng API đầu vào khác, nguyên tắc của **while** vẫn giống nhau: cập nhật dữ liệu được kiểm tra trước lần đánh giá điều kiện tiếp theo.

### 3.2. Vòng lặp while vô hạn

Có thể viết vòng lặp chạy liên tục bằng điều kiện luôn đúng:

~~~java
while (true) {
    String command = IO.readln("Nhập exit để kết thúc: ");

    if (command == null || command.equalsIgnoreCase("exit")) {
        break;
    }

    IO.println("Đang xử lý: " + command);
}
~~~

Vòng lặp chỉ kết thúc khi lệnh **break** được thực hiện. Đây là cấu trúc thường gặp trong vòng lặp xử lý lệnh hoặc chương trình tương tác đơn giản.

## 4. Vòng lặp do-while

Dùng **do-while** khi thân vòng lặp cần chạy ít nhất một lần trước khi kiểm tra điều kiện. Khác với **while**, điều kiện được đặt ở cuối.

Cú pháp:

~~~java
do {
    // thân vòng lặp
} while (điều_kiện);
~~~

Chú ý dấu chấm phẩy sau **while (điều_kiện);**. Dấu này là một phần bắt buộc của cú pháp.

Ví dụ:

~~~java
int count = 1;

do {
    System.out.println(count);
    count++;
} while (count <= 5);
~~~

Kết quả là các số từ 1 đến 5.

Ngay cả khi điều kiện sai ngay từ đầu, thân **do-while** vẫn được thực hiện một lần:

~~~java
int value = 10;

do {
    System.out.println("Giá trị: " + value);
} while (value < 5);
~~~

Chương trình vẫn in **Giá trị: 10**, sau đó mới kiểm tra điều kiện và kết thúc.

### 4.1. Trường hợp sử dụng: menu hoặc xác nhận đầu vào

Một menu cần hiển thị ít nhất một lần thường phù hợp với **do-while**:

~~~java
int choice;

do {
    IO.println("1. Xem thông tin");
    IO.println("2. Cập nhật thông tin");
    IO.println("0. Thoát");

    String input = IO.readln("Chọn chức năng: ");

    if (input == null) {
        choice = 0;
    } else {
        try {
            choice = Integer.parseInt(input);
        } catch (NumberFormatException exception) {
            choice = -1;
        }
    }

    switch (choice) {
        case 1 -> IO.println("Đang xem thông tin...");
        case 2 -> IO.println("Đang cập nhật thông tin...");
        case 0 -> IO.println("Tạm biệt.");
        default -> IO.println("Lựa chọn không hợp lệ.");
    }
} while (choice != 0);
~~~

Menu được hiển thị trước khi chương trình kiểm tra lựa chọn có yêu cầu thoát hay không. Nếu người dùng nhập sai, chương trình hiển thị thông báo và quay lại menu.

**do-while** cũng phù hợp khi cần yêu cầu người dùng nhập lại dữ liệu ít nhất một lần. Nếu có thể xác định ngay từ đầu rằng không cần thực hiện công việc, **while** thường phù hợp hơn.

## 5. Vòng lặp enhanced for

**Enhanced for**, còn gọi là *for-each loop*, dùng để duyệt lần lượt từng phần tử trong một mảng hoặc một đối tượng triển khai **Iterable**. Dạng này giúp mã nguồn dễ đọc khi bạn chỉ cần xử lý từng phần tử và không cần tự quản lý chỉ số hay iterator.

Cú pháp:

~~~java
for (KiểuPhầnTử phầnTử : mảng_hoặc_iterable) {
    // xử lý phần tử hiện tại
}
~~~

Ví dụ duyệt mảng:

~~~java
String[] languages = {"Java", "Kotlin", "Scala"};

for (String language : languages) {
    System.out.println(language);
}
~~~

Kết quả:

~~~text
Java
Kotlin
Scala
~~~

Ở mỗi lượt, biến **language** nhận giá trị của phần tử tiếp theo. Khi không còn phần tử, vòng lặp kết thúc.

### 5.1. Duyệt collection

Các collection phổ biến như **List**, **Set** và **Queue** triển khai **Iterable**, vì vậy có thể dùng enhanced for:

~~~java
List<String> students = List.of("An", "Bình", "Chi");

for (String student : students) {
    System.out.println("Học viên: " + student);
}
~~~

Có thể dùng **var** để trình biên dịch suy luận kiểu phần tử từ mảng hoặc Iterable:

~~~java
var scores = List.of(8, 9, 10);

for (var score : scores) {
    System.out.println(score);
}
~~~

Dùng kiểu tường minh khi kiểu dữ liệu giúp người đọc hiểu mục đích của biến. Dùng **var** khi kiểu đã rõ từ biểu thức bên phải và việc lặp lại tên kiểu không giúp ích.

### 5.2. Duyệt Map

**Map** không triển khai **Iterable**, vì vậy không thể duyệt trực tiếp bằng enhanced for. Hãy chọn view phù hợp với dữ liệu cần xử lý:

- **entrySet()** khi cần cả khóa và giá trị.
- **keySet()** khi chỉ cần khóa.
- **values()** khi chỉ cần giá trị.

Ví dụ duyệt cả khóa và giá trị:

~~~java
Map<String, Integer> scores = Map.of(
    "An", 8,
    "Bình", 9,
    "Chi", 10
);

for (Map.Entry<String, Integer> entry : scores.entrySet()) {
    System.out.println(entry.getKey() + ": " + entry.getValue());
}
~~~

Nếu chỉ cần giá trị:

~~~java
for (int score : scores.values()) {
    System.out.println(score);
}
~~~

**Map.values()** trả về các giá trị kiểu **Integer**; biến **int** nhận giá trị thông qua unboxing. Nếu collection chứa phần tử null, việc unbox sang kiểu nguyên thủy có thể gây **NullPointerException**. Hãy dùng kiểu tham chiếu hoặc kiểm tra null khi dữ liệu có thể chứa null.

### 5.3. Enhanced for hoạt động như thế nào?

Java định nghĩa enhanced for cho hai nhóm dữ liệu:

1. **Mảng**: phần tử được lấy lần lượt theo chỉ số từ đầu đến cuối mảng.
2. **Iterable**: Java sử dụng iterator của đối tượng, lần lượt gọi **hasNext()** và **next()** để lấy phần tử.

Điều này giải thích vì sao một collection triển khai **Iterable** có thể được duyệt bằng enhanced for mà không cần gọi iterator bằng tay.

Enhanced for không nhận trực tiếp một **Stream** vì **Stream** không triển khai **Iterable**. Với dữ liệu dạng stream, hãy dùng các thao tác của Stream API như **forEach**, **map**, **filter** hoặc chuyển kết quả sang một collection khi cần duyệt bằng enhanced for.

### 5.4. Giới hạn của biến phần tử

Biến khai báo trong enhanced for là biến cục bộ nhận giá trị của phần tử hiện tại. Gán lại biến đó không thay thế phần tử bên trong mảng hoặc collection.

~~~java
int[] numbers = {1, 2, 3};

for (int number : numbers) {
    number = 0;
}

System.out.println(Arrays.toString(numbers));
~~~

Mảng vẫn chứa **[1, 2, 3]**, bởi **number** chỉ là biến cục bộ nhận bản sao giá trị kiểu nguyên thủy.

Với phần tử là đối tượng, biến lặp nhận một bản sao tham chiếu đến đối tượng. Bạn có thể gọi method làm thay đổi trạng thái của chính đối tượng đó, nhưng gán biến lặp sang một đối tượng khác cũng không thay thế phần tử trong collection.

Nếu cần thay đổi phần tử theo vị trí trong mảng, hãy dùng **for** cơ bản với chỉ số. Nếu cần thay đổi nội dung collection, hãy dùng API phù hợp của collection hoặc **ListIterator** khi cần cập nhật tại vị trí duyệt.

### 5.5. Không cấu trúc lại collection khi đang enhanced for

Enhanced for trên một **Iterable** sử dụng iterator. Nếu thêm hoặc xóa phần tử trực tiếp khỏi collection trong lúc đang duyệt, iterator của nhiều collection chuẩn có thể phát hiện thay đổi và ném **ConcurrentModificationException**.

Ví dụ cần tránh:

~~~java
List<String> names = new ArrayList<>(List.of("An", "Bình", "Chi", "Dung"));

for (String name : names) {
    if (name.startsWith("B")) {
        names.remove(name); // Có thể gây ConcurrentModificationException
    }
}
~~~

Nếu muốn xóa phần tử theo điều kiện, có thể dùng **removeIf**:

~~~java
names.removeIf(name -> name.startsWith("B"));
~~~

Hoặc dùng **Iterator** tường minh khi cần điều khiển việc xóa trong lúc duyệt:

~~~java
Iterator<String> iterator = names.iterator();

while (iterator.hasNext()) {
    String name = iterator.next();

    if (name.startsWith("B")) {
        iterator.remove();
    }
}
~~~

Fail-fast là cơ chế phát hiện lỗi trong nhiều iterator của collection, không phải bảo đảm đồng bộ hóa giữa nhiều luồng. Không dựa vào việc có hay không có **ConcurrentModificationException** để điều phối truy cập đồng thời.

## 6. break và continue trong vòng lặp

Hai câu lệnh này thay đổi luồng thực hiện bên trong vòng lặp:

- **break** kết thúc vòng lặp gần nhất đang bao quanh nó.
- **continue** bỏ qua phần còn lại của lượt hiện tại và chuyển sang điểm tiếp tục của vòng lặp.

### 6.1. break: kết thúc vòng lặp

Ví dụ tìm một giá trị trong mảng:

~~~java
int[] numbers = {4, 8, 12, 16, 20};
int target = 12;
int foundAt = -1;

for (int i = 0; i < numbers.length; i++) {
    if (numbers[i] == target) {
        foundAt = i;
        break;
    }
}

System.out.println("Vị trí tìm thấy: " + foundAt);
~~~

Khi tìm thấy **target**, lệnh **break** kết thúc vòng **for** ngay lập tức. Những phần tử sau đó không được kiểm tra.

Lệnh **break** không nhãn chỉ thoát khỏi vòng **for**, **while**, **do-while** hoặc **switch** gần nhất. Vì vậy, nếu một vòng lặp chứa **switch**, **break** đặt bên trong nhánh switch sẽ thoát khỏi switch, không tự động thoát khỏi vòng lặp bao quanh.

### 6.2. continue: bỏ qua lượt hiện tại

Ví dụ chỉ tính tổng các số dương:

~~~java
int[] values = {-2, 5, 0, 7, -1};
int sum = 0;

for (int value : values) {
    if (value <= 0) {
        continue;
    }

    sum += value;
}

System.out.println("Tổng số dương: " + sum);
~~~

Khi **value** nhỏ hơn hoặc bằng 0, **continue** bỏ qua phần còn lại của thân vòng lặp và chuyển sang phần tử tiếp theo.

Điểm tiếp tục phụ thuộc loại vòng lặp:

| Vòng lặp | Sau khi gặp continue |
|---|---|
| **for** cơ bản | Chạy phần cập nhật, rồi kiểm tra điều kiện |
| **while** | Kiểm tra lại điều kiện |
| **do-while** | Kiểm tra điều kiện ở cuối |
| **enhanced for** | Chuyển sang phần tử tiếp theo |

Điểm khác biệt của **for** cơ bản rất quan trọng. Phần cập nhật vẫn chạy khi **continue** được thực hiện. Nếu dùng **while**, bạn phải tự bảo đảm trạng thái được cập nhật trước khi quay lại điều kiện.

Ví dụ dễ tạo vòng lặp vô hạn:

~~~java
int i = 0;

while (i < 5) {
    if (i == 2) {
        continue; // i không tăng, điều kiện luôn đúng
    }

    i++;
}
~~~

Khi **i** bằng 2, chương trình liên tục quay lại điều kiện mà không thay đổi **i**. Có thể sửa bằng cách cập nhật trước **continue** hoặc viết lại logic để mọi nhánh đều tiến đến trạng thái kết thúc.

### 6.3. break và continue có nhãn

Trong vòng lặp lồng nhau, **break** và **continue** không nhãn chỉ tác động đến vòng lặp gần nhất. Java cho phép đặt nhãn trước một câu lệnh để điều khiển một vòng lặp bên ngoài.

Ví dụ thoát cả hai vòng lặp khi tìm thấy một phần tử:

~~~java
int[][] matrix = {
    {1, 2, 3},
    {4, 5, 6},
    {7, 8, 9}
};

int target = 5;
int rowFound = -1;
int columnFound = -1;

search:
for (int row = 0; row < matrix.length; row++) {
    for (int column = 0; column < matrix[row].length; column++) {
        if (matrix[row][column] == target) {
            rowFound = row;
            columnFound = column;
            break search;
        }
    }
}

System.out.println("Tìm thấy tại: " + rowFound + ", " + columnFound);
~~~

**break search** kết thúc câu lệnh được gắn nhãn **search**, tức vòng **for** bên ngoài. Luồng điều khiển tiếp tục tại câu lệnh ngay sau vòng lặp đó.

**continue search** sẽ bỏ qua phần còn lại của lượt hiện tại của vòng lặp bên ngoài và bắt đầu lượt tiếp theo của vòng lặp đó. Nhãn của **continue** phải chỉ đến một câu lệnh lặp (**for**, **while** hoặc **do-while**).

Nhãn hữu ích trong một số thuật toán duyệt ma trận hoặc tìm kiếm. Nếu logic trở nên khó đọc, hãy cân nhắc tách phần xử lý thành method để dùng **return** khi tìm được kết quả.

## 7. Vòng lặp lồng nhau

Một vòng lặp có thể nằm trong thân của vòng lặp khác. Cách này thường dùng để xử lý bảng, ma trận, cặp phần tử hoặc các tổ hợp.

Ví dụ in bảng nhân từ 1 đến 3:

~~~java
for (int row = 1; row <= 3; row++) {
    for (int column = 1; column <= 3; column++) {
        System.out.print(row * column + "\t");
    }

    System.out.println();
}
~~~

Vòng ngoài chọn hàng. Với mỗi hàng, vòng trong chạy đủ các cột. Do đó, thân vòng trong được thực hiện 3 × 3 = 9 lần.

Nếu vòng ngoài chạy **m** lượt và vòng trong chạy **n** lượt cho mỗi lượt ngoài, tổng số lần thực hiện thân trong thường là **m × n**. Với dữ liệu lớn, số vòng lặp lồng nhau ảnh hưởng trực tiếp đến thời gian xử lý.

Duyệt mảng hai chiều cũng có thể dùng enhanced for lồng nhau:

~~~java
int[][] matrix = {
    {1, 2, 3},
    {4, 5, 6}
};

for (int[] row : matrix) {
    for (int value : row) {
        System.out.print(value + " ");
    }

    System.out.println();
}
~~~

Với mảng hai chiều Java, mỗi phần tử của mảng ngoài là một mảng con. Các mảng con có thể có độ dài khác nhau, vì vậy nên dùng **row.length** khi cần truy cập theo chỉ số của từng hàng.

## 8. Chọn loại vòng lặp phù hợp

| Nhu cầu | Nên dùng | Lý do |
|---|---|---|
| Lặp theo số lần hoặc cần chỉ số | **for** cơ bản | Khởi tạo, điều kiện và cập nhật nằm cùng một nơi |
| Lặp đến khi trạng thái hoặc dữ liệu thay đổi | **while** | Điều kiện được kiểm tra trước mỗi lượt |
| Thân cần thực hiện ít nhất một lần | **do-while** | Điều kiện được kiểm tra sau thân |
| Xử lý từng phần tử của mảng hoặc Iterable | **enhanced for** | Không phải tự quản lý chỉ số hoặc iterator |
| Cần xóa phần tử trong lúc duyệt collection | **Iterator** hoặc **removeIf** | Kiểm soát thao tác cập nhật collection đúng cách |
| Duyệt nhiều chiều hoặc các cặp phần tử | Vòng lặp lồng nhau | Mỗi vòng đảm nhiệm một chiều xử lý |

Không có loại vòng lặp nào luôn tốt nhất. Hãy chọn cấu trúc thể hiện rõ nhất điều kiện dừng, dữ liệu cần duyệt và thao tác cập nhật.

## 9. Các lỗi thường gặp

| Lỗi | Nguyên nhân và cách sửa |
|---|---|
| Điều kiện dùng **i <= array.length** | Chỉ số hợp lệ cuối cùng là **array.length - 1**; dùng **i < array.length**. |
| Quên cập nhật biến trong **while** | Điều kiện có thể luôn đúng; cập nhật trạng thái trong mọi đường đi cần thiết. |
| Đặt dấu chấm phẩy ngay sau **while** hoặc **for** | Ví dụ **while (condition);** tạo thân rỗng; chỉ dùng câu lệnh rỗng khi thật sự cần. |
| Quên dấu chấm phẩy sau điều kiện **do-while** | Cú pháp yêu cầu **while (condition);**. |
| Nhầm **break** với **continue** | **break** kết thúc vòng lặp; **continue** chỉ bỏ qua lượt hiện tại. |
| Dùng **continue** trong **while** nhưng quên cập nhật biến | Có thể quay lại điều kiện với cùng trạng thái và lặp vô hạn. |
| Nghĩ enhanced for cung cấp chỉ số | Enhanced for chỉ cung cấp phần tử; dùng **for** cơ bản nếu cần chỉ số. |
| Dùng enhanced for trực tiếp với **Map** hoặc **Stream** | **Map** và **Stream** không phải **Iterable**; dùng **entrySet()**, **keySet()**, **values()** hoặc thao tác Stream API. |
| Gán lại biến phần tử và mong collection thay đổi | Biến lặp là biến cục bộ; dùng chỉ số, iterator hoặc API cập nhật phù hợp. |
| Thêm hoặc xóa phần tử collection trực tiếp khi enhanced for đang chạy | Iterator có thể phát hiện thay đổi và ném **ConcurrentModificationException**; dùng **removeIf** hoặc **Iterator.remove()**. |
| Dùng **==** để so sánh chuỗi dừng vòng lặp | **==** so sánh tham chiếu; dùng **equals** hoặc **equalsIgnoreCase** để so sánh nội dung chuỗi. |

### 9.1. Kiểm tra biên của vòng lặp

Với mảng có **length** phần tử, chỉ số hợp lệ bắt đầu từ 0 và kết thúc ở **length - 1**.

~~~java
int[] values = {10, 20, 30};

for (int i = 0; i < values.length; i++) {
    System.out.println(values[i]);
}
~~~

Nếu thay **<** bằng **<=**, vòng lặp sẽ truy cập **values[values.length]**, dẫn đến **ArrayIndexOutOfBoundsException**.

### 9.2. Kiểm tra điều kiện kết thúc

Khi viết vòng lặp, hãy xác định rõ:

- Biến hoặc trạng thái nào quyết định việc tiếp tục?
- Trạng thái đó thay đổi ở đâu?
- Có đường đi nào bỏ qua cập nhật không?
- Điều kiện có thể sai ngay từ đầu không?
- Vòng lặp có cần chạy ít nhất một lần không?

Trả lời các câu hỏi này giúp tránh phần lớn lỗi lặp vô hạn và lỗi lệch một đơn vị.

## 10. Ví dụ tổng hợp: tính điểm trung bình và tìm điểm cao nhất

Ví dụ dưới đây dùng compact source file và **IO.println** có trong Java 27. Chương trình duyệt danh sách điểm bằng enhanced for, tính tổng, đếm số điểm và tìm điểm lớn nhất:

~~~java
void main() {
    List<Integer> scores = List.of(8, 9, 7, 10, 6);

    int total = 0;
    int count = 0;
    int highest = Integer.MIN_VALUE;

    for (int score : scores) {
        if (score < 0 || score > 10) {
            continue;
        }

        total += score;
        count++;

        if (score > highest) {
            highest = score;
        }
    }

    if (count == 0) {
        IO.println("Không có điểm hợp lệ.");
    } else {
        double average = (double) total / count;

        IO.println("Số điểm hợp lệ: " + count);
        IO.println("Điểm trung bình: " + average);
        IO.println("Điểm cao nhất: " + highest);
    }
}
~~~

Kết quả:

~~~text
Số điểm hợp lệ: 5
Điểm trung bình: 8.0
Điểm cao nhất: 10
~~~

Trong ví dụ này, enhanced for phù hợp vì chương trình cần xử lý mọi phần tử và không cần vị trí của từng điểm. **continue** bỏ qua điểm nằm ngoài phạm vi hợp lệ. Sau vòng lặp, chương trình kiểm tra số phần tử hợp lệ trước khi chia để tránh phép chia cho 0.

Có thể chạy mã trên bằng cách lưu vào tệp **ScoreSummary.java** và thực hiện:

~~~bash
java ScoreSummary.java
~~~

## 11. Ghi nhớ

- **for** cơ bản phù hợp khi cần bộ đếm, chỉ số hoặc phần khởi tạo, điều kiện và cập nhật rõ ràng.
- **while** kiểm tra điều kiện trước thân; thân có thể không chạy lần nào.
- **do-while** chạy thân trước khi kiểm tra điều kiện; thân luôn chạy ít nhất một lần và câu lệnh kết thúc bằng dấu chấm phẩy.
- **enhanced for** duyệt lần lượt phần tử của mảng hoặc đối tượng triển khai **Iterable**.
- **Map** không phải **Iterable**; dùng **entrySet()**, **keySet()** hoặc **values()** để duyệt.
- Gán lại biến phần tử trong enhanced for không thay thế phần tử của mảng hoặc collection.
- **break** kết thúc vòng lặp mục tiêu; **continue** chuyển sang lượt tiếp theo.
- Trong **for** cơ bản, phần cập nhật vẫn chạy sau **continue**; trong **while** và **do-while**, điều kiện được đánh giá lại theo vị trí của nó.
- Vòng lặp lồng nhau hữu ích cho dữ liệu nhiều chiều, nhưng số lượt thực hiện tăng theo tích số lượt của các vòng.
- Luôn xác định điều kiện dừng và cập nhật trạng thái để tránh vòng lặp vô hạn.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 27 — Chapter 14: Blocks, Statements, and Patterns](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-14.html)
- [Java Language Specification, Java SE 27 — §14.12 while, §14.13 do, §14.14 for, §14.15 break, §14.16 continue](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-14.html)
- [Dev.java — Control Flow Statements](https://dev.java/learn/language/constructs/basics/controlling-flow/)
- [Java SE 27 API — java.lang.Iterable](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Iterable.html)
- [Java SE 27 API — java.util.Iterator](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Iterator.html)
- [Java SE 27 API — java.util.Collection](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Collection.html)
