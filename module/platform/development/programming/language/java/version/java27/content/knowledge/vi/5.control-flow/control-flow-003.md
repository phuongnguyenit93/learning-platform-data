# Break, continue và điều kiện kết thúc vòng lặp

Trong Java 27, vòng lặp cho phép thực hiện một khối lệnh nhiều lần. Điều kiện của vòng lặp quyết định khi nào việc lặp tiếp tục hoặc kết thúc; hai câu lệnh **break** và **continue** cho phép thay đổi luồng thực thi ngay trong thân vòng lặp.

- **break** kết thúc vòng lặp hoặc câu lệnh **switch** gần nhất phù hợp.
- **continue** bỏ qua phần còn lại của lần lặp hiện tại và chuyển sang bước kiểm tra hoặc lần lặp tiếp theo.
- **break** và **continue** có thể đi kèm nhãn (label) để điều khiển câu lệnh được gắn nhãn, thường là một vòng lặp bên ngoài trong cấu trúc lồng nhau.

Bài viết trình bày cách sử dụng các câu lệnh này với **for**, **while**, **do-while**, enhanced **for** và **switch**, đồng thời giải thích cách thiết kế điều kiện dừng để tránh vòng lặp vô hạn ngoài ý muốn.

## 1. Vòng lặp kết thúc như thế nào?

Một vòng lặp thông thường tiếp tục khi điều kiện lặp còn đúng và kết thúc khi điều kiện trở thành sai. Java có bốn dạng vòng lặp thường dùng:

| Loại vòng lặp | Thời điểm kiểm tra điều kiện | Số lần thân vòng lặp có thể chạy |
|---|---|---|
| **while** | Trước mỗi lần chạy thân vòng lặp | Có thể là 0 lần |
| **do-while** | Sau mỗi lần chạy thân vòng lặp | Ít nhất 1 lần |
| **for** | Trước mỗi lần chạy thân vòng lặp | Có thể là 0 lần |
| Enhanced **for** | Theo từng phần tử của mảng hoặc đối tượng **Iterable** | 0 lần nếu không có phần tử |

### while

Vòng lặp **while** kiểm tra điều kiện trước khi chạy thân vòng lặp. Nếu điều kiện ban đầu là **false**, thân vòng lặp không chạy lần nào.

~~~java
int count = 0;

while (count < 3) {
    System.out.println(count);
    count++;
}
~~~

Kết quả:

~~~text
0
1
2
~~~

Mỗi lần lặp, **count** tăng lên 1. Khi **count** đạt 3, điều kiện **count < 3** sai và vòng lặp kết thúc.

### do-while

Vòng lặp **do-while** chạy thân vòng lặp trước rồi mới kiểm tra điều kiện. Vì vậy, thân vòng lặp luôn chạy ít nhất một lần.

~~~java
int count = 0;

do {
    System.out.println(count);
    count++;
} while (count < 3);
~~~

Điểm cú pháp cần nhớ: câu lệnh **do-while** kết thúc bằng dấu chấm phẩy sau biểu thức điều kiện.

### for

Vòng lặp **for** truyền thống gồm ba phần: khởi tạo, điều kiện và cập nhật:

~~~java
for (int index = 0; index < 3; index++) {
    System.out.println(index);
}
~~~

Thứ tự thực thi:

1. Phần khởi tạo chạy một lần trước vòng lặp.
2. Điều kiện được kiểm tra.
3. Nếu điều kiện đúng, thân vòng lặp chạy.
4. Phần cập nhật chạy sau thân vòng lặp.
5. Quay lại bước kiểm tra điều kiện.

Nếu điều kiện sai ngay từ đầu, thân vòng lặp không chạy. Phần khởi tạo và cập nhật có thể chứa nhiều biểu thức, nhưng nên giữ mã đơn giản để dễ hiểu thứ tự thực thi.

### Enhanced for

Enhanced **for** duyệt lần lượt các phần tử của mảng hoặc đối tượng triển khai **Iterable**:

~~~java
String[] languages = {"Java", "Kotlin", "Scala"};

for (String language : languages) {
    System.out.println(language);
}
~~~

Vòng lặp kết thúc tự nhiên khi đã duyệt hết phần tử. Dùng **break** để dừng sớm hoặc **continue** để bỏ qua phần còn lại của lần xử lý phần tử hiện tại.

## 2. break: kết thúc vòng lặp hoặc switch

Câu lệnh **break** không có nhãn kết thúc câu lệnh **switch** hoặc vòng lặp gần nhất đang chứa nó. Chương trình tiếp tục tại câu lệnh ngay sau cấu trúc vừa kết thúc.

### break trong vòng lặp

Ví dụ tìm phần tử đầu tiên thỏa mãn điều kiện:

~~~java
int[] numbers = {4, 8, 15, 16, 23, 42};
int target = 15;
int found = -1;

for (int number : numbers) {
    if (number == target) {
        found = number;
        break;
    }
}

System.out.println(found);
~~~

Khi tìm thấy **15**, câu lệnh **break** kết thúc vòng lặp. Các phần tử còn lại không được duyệt. Nếu không có phần tử phù hợp, vòng lặp kết thúc tự nhiên và **found** vẫn giữ giá trị **-1**.

Dùng **break** khi đã có đủ kết quả hoặc không cần tiếp tục thực hiện các lần lặp còn lại, ví dụ:

- Tìm thấy phần tử cần tìm.
- Đã đạt giới hạn số lần thử.
- Phát hiện điều kiện khiến các bước tiếp theo không còn cần thiết.
- Đã đọc được dấu hiệu kết thúc trong một luồng dữ liệu.

### break trong switch statement

Trong dạng **switch** dùng nhãn **case** và dấu hai chấm, **break** thường được dùng để kết thúc nhánh hiện tại và thoát khỏi câu lệnh **switch**:

~~~java
int statusCode = 404;

switch (statusCode) {
    case 200:
        System.out.println("Success");
        break;
    case 404:
        System.out.println("Not found");
        break;
    default:
        System.out.println("Other status");
}
~~~

Nếu bỏ **break** trong switch dạng này, luồng thực thi có thể đi tiếp sang nhãn **case** kế tiếp (fall-through), trừ những trường hợp mà quy tắc của Java không cho phép. Đây có thể là hành vi có chủ ý, nhưng thường là nguyên nhân gây lỗi khi người viết quên **break**.

Java hiện cũng hỗ trợ switch dùng nhãn mũi tên:

~~~java
switch (statusCode) {
    case 200 -> System.out.println("Success");
    case 404 -> System.out.println("Not found");
    default -> System.out.println("Other status");
}
~~~

Mỗi switch rule dạng mũi tên chỉ thực thi nhánh tương ứng, không tự động fall-through sang nhánh tiếp theo; do đó không cần thêm **break** chỉ để ngăn chạy xuyên qua các nhánh.

Với switch expression dùng để tạo ra một giá trị, dùng **yield** trong khối của nhánh khi cần trả về giá trị của nhánh:

~~~java
String description = switch (statusCode) {
    case 200 -> "Success";
    case 404 -> "Not found";
    default -> {
        String message = "HTTP status " + statusCode;
        yield message;
    }
};
~~~

**yield** cung cấp kết quả cho switch expression. Nó không phải câu lệnh thay thế chung cho **break** trong vòng lặp hoặc switch statement.

Khi **switch** nằm bên trong vòng lặp, cần phân biệt đích của hai câu lệnh:

- **break** không nhãn thoát khỏi **switch** gần nhất; vòng lặp bao quanh vẫn tiếp tục.
- **continue** không nhãn tìm vòng lặp gần nhất đang bao quanh, vì **switch** không phải là vòng lặp. Do đó, **continue** trong một nhánh switch có thể chuyển sang lần lặp kế tiếp của vòng lặp chứa switch.

~~~java
int[] values = {0, 1, 2};

for (int value : values) {
    switch (value) {
        case 0:
            System.out.println("Switch finished for zero");
            break;
        case 1:
            System.out.println("Skip the rest for one");
            continue;
        default:
            System.out.println("Process " + value);
    }

    System.out.println("After switch: " + value);
}
~~~

Trong ví dụ này, **break** trong nhánh switch statement kết thúc switch cho **value** bằng 0 rồi chạy câu lệnh **After switch**. **continue** trong nhánh switch với **value** bằng 1 chuyển tới phần tử tiếp theo của vòng lặp, nên câu lệnh **After switch** bị bỏ qua ở lượt đó.

## 3. continue: bỏ qua phần còn lại của lần lặp

Câu lệnh **continue** bỏ qua các câu lệnh còn lại trong thân vòng lặp hiện tại và chuyển sang bước tiếp theo của chính vòng lặp đó. Nó không kết thúc toàn bộ vòng lặp.

### continue trong while

~~~java
int number = 0;

while (number < 6) {
    number++;

    if (number % 2 == 0) {
        continue;
    }

    System.out.println(number);
}
~~~

Kết quả:

~~~text
1
3
5
~~~

Khi **number** là số chẵn, **continue** bỏ qua lệnh in. Luồng thực thi quay lại kiểm tra điều kiện **while**.

Với **while**, cần cập nhật biến điều khiển trước một lệnh **continue** nếu việc cập nhật đó cần thiết để vòng lặp tiến tới điều kiện kết thúc. Nếu đặt lệnh cập nhật sau **continue**, lần lặp có thể không bao giờ tiến triển.

Ví dụ sai về logic:

~~~java
int number = 0;

while (number < 5) {
    if (number == 2) {
        continue;
    }

    number++;
}
~~~

Khi **number** bằng 2, chương trình liên tục quay lại đầu vòng lặp mà không tăng **number**. Điều kiện **number < 5** luôn đúng và vòng lặp không kết thúc.

Có thể sửa bằng cách cập nhật trước khi kiểm tra:

~~~java
int number = 0;

while (number < 5) {
    number++;

    if (number == 2) {
        continue;
    }

    System.out.println(number);
}
~~~

### continue trong for

Với vòng lặp **for** truyền thống, **continue** chuyển tới phần cập nhật rồi mới kiểm tra điều kiện tiếp theo:

~~~java
for (int number = 0; number < 6; number++) {
    if (number % 2 == 0) {
        continue;
    }

    System.out.println(number);
}
~~~

Kết quả:

~~~text
1
3
5
~~~

Trong ví dụ này, khi **continue** được thực thi, biểu thức **number++** vẫn chạy. Đây là điểm khác biệt quan trọng khi so sánh với ví dụ **while**: phần cập nhật của **for** nằm trong cấu trúc điều khiển của vòng lặp.

### continue trong do-while

Với **do-while**, **continue** chuyển tới bước kiểm tra điều kiện ở cuối vòng lặp:

~~~java
int number = 0;

do {
    number++;

    if (number % 2 == 0) {
        continue;
    }

    System.out.println(number);
} while (number < 5);
~~~

Ngay cả khi gặp **continue**, điều kiện **number < 5** vẫn được kiểm tra. Nếu biến điều khiển không được cập nhật trước **continue**, cần xem xét liệu điều kiện có thể trở thành sai hay không để tránh lặp vô hạn.

### continue trong enhanced for

Trong enhanced **for**, **continue** bỏ qua phần còn lại của lần xử lý phần tử hiện tại và chuyển sang phần tử kế tiếp:

~~~java
String[] names = {"An", "", "Binh", "Chi"};

for (String name : names) {
    if (name.isBlank()) {
        continue;
    }

    System.out.println(name);
}
~~~

Kết quả:

~~~text
An
Binh
Chi
~~~

## 4. break và continue trong vòng lặp lồng nhau

Khi một vòng lặp nằm bên trong vòng lặp khác, **break** và **continue** không có nhãn chỉ tác động tới vòng lặp gần nhất đang chứa câu lệnh đó.

### break không nhãn chỉ thoát vòng lặp trong cùng

~~~java
for (int row = 1; row <= 3; row++) {
    for (int column = 1; column <= 3; column++) {
        if (column == 2) {
            break;
        }

        System.out.println(row + ":" + column);
    }
}
~~~

Kết quả:

~~~text
1:1
2:1
3:1
~~~

Mỗi lần **column** đạt 2, vòng lặp trong kết thúc. Vòng lặp ngoài tiếp tục với giá trị **row** tiếp theo.

### continue không nhãn chỉ tiếp tục vòng lặp trong cùng

~~~java
for (int row = 1; row <= 2; row++) {
    for (int column = 1; column <= 3; column++) {
        if (column == 2) {
            continue;
        }

        System.out.println(row + ":" + column);
    }
}
~~~

Kết quả:

~~~text
1:1
1:3
2:1
2:3
~~~

Ở đây, **continue** bỏ qua phần còn lại của lần lặp có **column** bằng 2, rồi vòng lặp trong tiếp tục với cột kế tiếp. Vòng lặp ngoài vẫn hoạt động bình thường.

## 5. Nhãn và break có nhãn

Nhãn (label) là tên được đặt trước một câu lệnh và kết thúc bằng dấu hai chấm. Trong cấu trúc lồng nhau, nhãn cho phép chỉ rõ câu lệnh cần thoát.

### break label để thoát vòng lặp bên ngoài

~~~java
search:
for (int row = 0; row < 3; row++) {
    for (int column = 0; column < 3; column++) {
        if (row == 1 && column == 2) {
            break search;
        }

        System.out.println(row + ":" + column);
    }
}

System.out.println("Search finished");
~~~

Khi điều kiện tìm kiếm đúng, **break search** kết thúc vòng lặp được gắn nhãn **search**, tức toàn bộ cấu trúc vòng lặp ngoài. Chương trình tiếp tục ở câu lệnh sau vòng lặp đó.

Lệnh **break label** có thể thoát khỏi câu lệnh được gắn nhãn đang bao quanh nó, kể cả một block thông thường:

~~~java
String input = "Java";

validation: {
    if (input == null) {
        break validation;
    }

    if (input.isBlank()) {
        break validation;
    }

    System.out.println("Input is valid");
}

System.out.println("Validation finished");
~~~

Ở ví dụ này, nhãn **validation** gắn với một block. **break validation** thoát block đó. Vì vậy, nhãn của **break** không bắt buộc phải gắn với vòng lặp; nó phải xác định một câu lệnh được gắn nhãn đang bao quanh vị trí **break**.

Không nên xem nhãn là một dạng **goto** tùy ý. **break label** chỉ chuyển luồng ra khỏi câu lệnh được gắn nhãn theo quy tắc của Java; nó không thể nhảy vào bên trong một block hoặc tới một vị trí tùy ý trong phương thức.

## 6. continue có nhãn để tiếp tục vòng lặp bên ngoài

**continue label** chuyển sang lần lặp tiếp theo của vòng lặp được gắn nhãn. Nhãn đích của **continue** phải gắn với một câu lệnh lặp như **for**, **while**, **do-while** hoặc enhanced **for**.

Ví dụ: duyệt một ma trận và bỏ qua phần còn lại của hàng hiện tại khi gặp giá trị không hợp lệ:

~~~java
int[][] matrix = {
    {1, 2, 3},
    {4, -1, 6},
    {7, 8, 9}
};

rows:
for (int row = 0; row < matrix.length; row++) {
    for (int column = 0; column < matrix[row].length; column++) {
        if (matrix[row][column] < 0) {
            continue rows;
        }

        System.out.println(matrix[row][column]);
    }
}
~~~

Kết quả:

~~~text
1
2
3
7
8
9
~~~

Khi gặp **-1**, **continue rows** kết thúc phần còn lại của lần lặp hàng hiện tại và chuyển tới bước tiếp theo của vòng lặp **rows**. Với vòng lặp **for** được gắn nhãn, phần cập nhật của vòng lặp ngoài được thực hiện trước khi kiểm tra điều kiện của lần lặp tiếp theo.

Một điểm quan trọng: nhãn phải đặt trực tiếp trước vòng lặp muốn tiếp tục. Nếu nhãn gắn với một block bao quanh vòng lặp, **continue** không thể dùng nhãn block đó làm đích.

~~~java
outerBlock: {
    // continue outerBlock; // Không hợp lệ: outerBlock không gắn với vòng lặp
    for (int i = 0; i < 3; i++) {
        System.out.println(i);
    }
}
~~~

Thông thường, chỉ nên dùng nhãn khi cần điều khiển rõ ràng một vòng lặp lồng nhau. Nếu có thể biểu đạt ý định bằng cách tách phương thức hoặc dùng một cấu trúc dữ liệu phù hợp, mã thường dễ đọc hơn.

## 7. Phân biệt break, continue, return và điều kiện vòng lặp

Các cách kết thúc luồng thực thi có phạm vi ảnh hưởng khác nhau:

| Câu lệnh hoặc tình huống | Tác động |
|---|---|
| Điều kiện vòng lặp trở thành **false** | Kết thúc vòng lặp hiện tại theo cách tự nhiên |
| **break** | Thoát vòng lặp hoặc switch gần nhất |
| **break label** | Thoát câu lệnh được gắn nhãn đang bao quanh |
| **continue** | Bỏ phần còn lại của lần lặp hiện tại và chuyển sang bước tiếp theo của vòng lặp gần nhất |
| **continue label** | Chuyển sang lần lặp tiếp theo của vòng lặp được gắn nhãn |
| **return** | Kết thúc phương thức hiện tại; nếu nằm trong thân vòng lặp thì vòng lặp cũng kết thúc theo |
| **throw** | Chuyển luồng sang xử lý ngoại lệ phù hợp; nếu không được xử lý tại phương thức hiện tại, phương thức kết thúc bất thường |

Ví dụ **return** kết thúc cả phương thức, không chỉ vòng lặp:

~~~java
int findFirstPositive(int[] values) {
    for (int value : values) {
        if (value > 0) {
            return value;
        }
    }

    return -1;
}
~~~

Khi tìm thấy số dương đầu tiên, **return** trả kết quả và kết thúc phương thức ngay lập tức. Không cần thêm **break** sau **return** vì câu lệnh phía sau sẽ không được thực thi.

Nếu chỉ muốn dừng vòng lặp nhưng vẫn cần chạy các câu lệnh phía sau vòng lặp, hãy dùng **break**:

~~~java
boolean found = false;

for (int value : values) {
    if (value > 0) {
        found = true;
        break;
    }
}

System.out.println("Found: " + found);
~~~

## 8. Thiết kế điều kiện kết thúc vòng lặp

Một vòng lặp có thể kết thúc tự nhiên khi điều kiện không còn đúng, hoặc kết thúc sớm bằng **break**. Để vòng lặp hoạt động đúng, cần xác định rõ điều kiện tiếp tục, biến điều khiển và cách tiến tới trạng thái kết thúc.

### Bảo đảm biến điều khiển có tiến triển

Với vòng lặp dựa trên bộ đếm, cần cập nhật bộ đếm theo hướng làm điều kiện cuối cùng trở thành sai:

~~~java
for (int attempt = 1; attempt <= 3; attempt++) {
    System.out.println("Attempt " + attempt);
}
~~~

Với **while**, cần tự cập nhật biến điều khiển trong thân vòng lặp:

~~~java
int remaining = 3;

while (remaining > 0) {
    System.out.println("Remaining: " + remaining);
    remaining--;
}
~~~

Nếu biến điều khiển không thay đổi, hoặc thay đổi theo hướng khiến điều kiện luôn đúng, vòng lặp có thể chạy vô hạn.

### Dùng break cho điều kiện kết thúc sớm

Có thể dùng **while (true)** khi điểm kết thúc phụ thuộc vào sự kiện xảy ra trong thân vòng lặp:

~~~java
int[] values = {3, 6, 9, 12};

int index = 0;
int total = 0;

while (true) {
    if (index == values.length) {
        break;
    }

    total += values[index];
    index++;
}

System.out.println(total);
~~~

Vòng lặp kết thúc khi **index** bằng độ dài mảng. Tuy nhiên, với ví dụ đơn giản này, vòng lặp **for** hoặc enhanced **for** thường ngắn gọn và ít có nguy cơ bỏ sót cập nhật hơn:

~~~java
int total = 0;

for (int value : values) {
    total += value;
}

System.out.println(total);
~~~

Chọn **while (true)** khi điều kiện kết thúc khó biểu đạt ở đầu vòng lặp, chẳng hạn một vòng xử lý sự kiện hoặc đọc dữ liệu cho tới khi nhận được dấu hiệu kết thúc. Khi dùng cách này, cần bảo đảm mọi đường thực thi phù hợp đều có khả năng đi tới điểm thoát.

### Dùng giá trị sentinel

Sentinel là một giá trị hoặc tín hiệu được quy ước để báo kết thúc dữ liệu. Ví dụ, xử lý một dãy số và dừng khi gặp giá trị âm:

~~~java
int[] inputs = {10, 20, 30, -1, 40};
int total = 0;

for (int input : inputs) {
    if (input < 0) {
        break;
    }

    total += input;
}

System.out.println(total); // 60
~~~

Giá trị sentinel cần được chọn sao cho không nhầm với dữ liệu hợp lệ theo quy ước của bài toán. Nếu dữ liệu không có giá trị sentinel phù hợp, có thể dùng một trạng thái riêng, chẳng hạn **Optional**, kết quả đọc dữ liệu hoặc một cờ kết thúc.

### Dùng continue để lọc phần tử

Khi muốn bỏ qua một số phần tử nhưng vẫn xử lý các phần tử còn lại, **continue** có thể làm rõ ý định:

~~~java
int[] scores = {8, -1, 9, 0, 10};
int total = 0;
int validCount = 0;

for (int score : scores) {
    if (score < 0) {
        continue;
    }

    total += score;
    validCount++;
}

if (validCount > 0) {
    System.out.println((double) total / validCount);
}
~~~

Các điểm số âm bị bỏ qua; các phần tử còn lại được cộng và đếm. Điều kiện kiểm tra **validCount > 0** tránh phép chia cho 0 khi không có dữ liệu hợp lệ.

## 9. Lỗi thường gặp khi dùng break và continue

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| **break** chỉ thoát vòng lặp trong cùng | **break** không nhãn luôn chọn vòng lặp hoặc switch gần nhất | Dùng **break label** nếu thật sự cần thoát cấu trúc bên ngoài |
| **continue** chỉ bỏ qua lần lặp của vòng lặp trong | **continue** không nhãn tác động lên vòng lặp gần nhất | Dùng **continue label** nếu cần chuyển sang lần lặp của vòng ngoài |
| Vòng lặp chạy vô hạn sau **continue** | Biến điều khiển trong **while** hoặc **do-while** không được cập nhật trước khi quay lại kiểm tra | Đưa cập nhật lên trước nhánh **continue** hoặc thiết kế lại điều kiện |
| Switch dạng dấu hai chấm chạy xuyên qua nhánh sau | Thiếu **break** khi không chủ ý fall-through | Thêm **break** hoặc dùng switch rule dạng mũi tên khi phù hợp |
| **continue label** không biên dịch | Nhãn đích không gắn với một câu lệnh lặp bao quanh | Gắn nhãn trực tiếp với vòng lặp cần tiếp tục |
| Dùng **break** sau **return** | **return** đã kết thúc phương thức | Xóa câu lệnh không thể được thực thi |
| Vòng lặp kết thúc trước khi xử lý đủ dữ liệu | Điều kiện dừng hoặc vị trí **break** quá rộng | Kiểm tra lại điều kiện và luồng xử lý của từng nhánh |

### Một số nguyên tắc thực hành

- Ưu tiên điều kiện vòng lặp thể hiện rõ khi nào cần tiếp tục.
- Dùng **break** khi đã tìm được kết quả hoặc không cần xử lý phần còn lại.
- Dùng **continue** khi muốn bỏ qua một lần xử lý và tiếp tục với phần tử hoặc lượt kế tiếp.
- Với vòng lặp lồng nhau, chỉ dùng nhãn khi nó làm rõ mục tiêu điều khiển; tránh đặt nhãn chung chung hoặc lạm dụng.
- Đảm bảo mọi nhánh **continue** trong **while** và **do-while** không bỏ qua thao tác cập nhật cần thiết.
- Kiểm tra trường hợp dữ liệu rỗng, không có phần tử phù hợp và điều kiện dừng xảy ra ngay ở lần đầu.
- Nếu logic thoát lặp trở nên khó đọc, cân nhắc tách phần xử lý thành phương thức có giá trị trả về rõ ràng.

## 10. Ví dụ tổng hợp: tìm kiếm trong ma trận

Ví dụ sau tìm một giá trị trong ma trận. Khi tìm thấy, chương trình thoát cả hai vòng lặp bằng **break label**; các giá trị âm được bỏ qua bằng **continue**:

~~~java
int[][] matrix = {
    {2, 4, 6},
    {8, -1, 10},
    {12, 14, 16}
};

int target = 10;
int foundRow = -1;
int foundColumn = -1;

search:
for (int row = 0; row < matrix.length; row++) {
    for (int column = 0; column < matrix[row].length; column++) {
        int value = matrix[row][column];

        if (value < 0) {
            continue;
        }

        if (value == target) {
            foundRow = row;
            foundColumn = column;
            break search;
        }
    }
}

if (foundRow >= 0) {
    System.out.println(
        "Found at row " + foundRow + ", column " + foundColumn
    );
} else {
    System.out.println("Not found");
}
~~~

Kết quả:

~~~text
Found at row 1, column 2
~~~

Trong ví dụ:

- Hai vòng **for** duyệt lần lượt từng hàng và cột.
- **continue** bỏ qua giá trị âm và tiếp tục duyệt cột tiếp theo.
- Khi tìm thấy giá trị cần tìm, chương trình lưu vị trí rồi dùng **break search** để thoát vòng lặp ngoài cùng.
- Sau vòng lặp, chương trình kiểm tra kết quả tìm kiếm và in thông tin tương ứng.

Khi sử dụng **break**, **continue** và điều kiện kết thúc, hãy luôn xác định câu lệnh nào là đích của luồng điều khiển, biến nào quyết định lần lặp tiếp theo và trường hợp nào bảo đảm vòng lặp dừng. Nắm rõ các quy tắc này giúp chương trình Java 27 xử lý vòng lặp chính xác, tránh bỏ sót dữ liệu và hạn chế lỗi lặp vô hạn.
