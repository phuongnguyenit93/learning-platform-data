# Mảng một chiều, nhiều chiều và thao tác bằng Arrays

Mảng (array) là cấu trúc dữ liệu dùng để lưu một số lượng phần tử có kiểu xác định, truy cập từng phần tử bằng chỉ số. Trong Java, mảng là đối tượng có độ dài cố định sau khi được tạo. Mỗi phần tử có cùng kiểu thành phần; kiểu đó có thể là kiểu nguyên thủy, kiểu tham chiếu hoặc chính một kiểu mảng khác.

Mảng phù hợp khi số lượng phần tử đã biết hoặc cần một vùng dữ liệu có cấu trúc đơn giản, truy cập nhanh theo chỉ số, chẳng hạn danh sách điểm, dãy số đo, bảng dữ liệu hoặc dữ liệu đầu vào/đầu ra của API. Java cung cấp lớp tiện ích **java.util.Arrays** để sắp xếp, tìm kiếm, sao chép, so sánh, điền giá trị và chuyển mảng thành Stream hoặc List view.

Bài viết áp dụng cho Java 27 và chỉ sử dụng các cú pháp, API còn được hỗ trợ. Các quy tắc ngôn ngữ được đối chiếu với [Java Language Specification 27 – Chapter 10: Arrays](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-10.html); các phương thức tiện ích được đối chiếu với [Java SE 27 API – java.util.Arrays](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Arrays.html).

## 1. Đặc điểm và cách khai báo mảng

### 1.1. Mảng là một đối tượng có độ dài cố định

Khai báo biến mảng chỉ tạo ra một biến tham chiếu. Mảng thực tế được tạo khi dùng biểu thức khởi tạo hoặc cú pháp tạo mảng:

~~~~java
int[] scores;                 // Chỉ khai báo biến tham chiếu
scores = new int[5];          // Tạo mảng gồm 5 phần tử int

int[] ages = new int[3];      // Khai báo và tạo mảng
String[] names = new String[4];
~~~~

Độ dài được xác định khi tạo mảng và không thể thay đổi. Muốn có nhiều hoặc ít phần tử hơn, chương trình phải tạo một mảng khác, thường sao chép dữ liệu cần giữ sang mảng mới. Vì thế, không thể gọi một phương thức kiểu add để tăng trực tiếp độ dài của mảng.

Mỗi mảng có trường **length** để lấy số phần tử:

~~~~java
int[] scores = new int[5];
System.out.println(scores.length); // 5
~~~~

Đây là trường, không phải phương thức: dùng **scores.length**, không dùng **scores.length()**. Mảng rỗng có thể có độ dài bằng 0, ví dụ **new int[0]**; trường hợp này khác với biến mảng đang mang giá trị **null**.

### 1.2. Cú pháp khai báo và khởi tạo

Nên đặt cặp dấu ngoặc vuông cạnh kiểu dữ liệu để dễ đọc:

~~~~java
int[] quantities;
double[] prices;
String[] productNames;

int[] primeNumbers = {2, 3, 5, 7, 11};
String[] weekdays = {"Monday", "Tuesday", "Wednesday"};
~~~~

Cũng có thể dùng cú pháp tạo mảng tường minh:

~~~~java
int[] values = new int[] {10, 20, 30};
~~~~

Khi đã có khai báo biến, có thể gán một biểu thức tạo mảng mới:

~~~~java
int[] values;
values = new int[] {10, 20, 30};
~~~~

Initializer trong dấu ngoặc nhọn tự xác định độ dài dựa trên số biểu thức khởi tạo. Các giá trị phải tương thích với kiểu phần tử của mảng. Dấu phẩy sau phần tử cuối cùng được phép dùng.

Tránh trộn hai kiểu đặt dấu ngoặc trong cùng một khai báo như **int values[]** và **int[] values**. Cả hai đều hợp lệ, nhưng cách đặt ngoặc sau kiểu dữ liệu thường làm rõ kiểu của từng biến hơn, nhất là khi khai báo nhiều biến cùng dòng.

### 1.3. Giá trị mặc định của phần tử

Khi tạo mảng bằng từ khóa **new** mà không cung cấp initializer, Java tự gán giá trị mặc định cho tất cả phần tử:

| Kiểu phần tử | Giá trị mặc định |
| --- | --- |
| byte, short, int, long | 0 |
| float, double | 0.0 |
| char | Ký tự NUL, mã Unicode U+0000 |
| boolean | false |
| Kiểu tham chiếu như String, Integer, đối tượng hoặc mảng con | null |

Ví dụ:

~~~~java
import java.util.Arrays;

int[] counts = new int[3];
String[] labels = new String[2];

System.out.println(Arrays.toString(counts)); // [0, 0, 0]
System.out.println(Arrays.toString(labels)); // [null, null]
~~~~

Giá trị mặc định giúp mảng luôn có phần tử được khởi tạo hợp lệ theo quy tắc của kiểu dữ liệu, nhưng với mảng tham chiếu, **null** có nghĩa là chưa có đối tượng được gán. Trước khi gọi phương thức trên một phần tử tham chiếu, cần bảo đảm phần tử đó không null.

### 1.4. Kiểu phần tử nguyên thủy và kiểu tham chiếu

Mảng kiểu nguyên thủy lưu trực tiếp giá trị của kiểu tương ứng:

~~~~java
int[] measurements = {12, 18, 25};
double[] ratios = {0.25, 0.5, 0.75};
boolean[] flags = {true, false, true};
~~~~

Mảng kiểu tham chiếu lưu các tham chiếu đến đối tượng:

~~~~java
String[] cities = {"Hanoi", "Da Nang", "Ho Chi Minh City"};
Integer[] retryCounts = {1, 2, 3};
~~~~

Mảng đối tượng không tự tạo các đối tượng ở từng vị trí. Ví dụ, **new String[3]** tạo một mảng có ba tham chiếu đang là null; chương trình phải gán từng đối tượng String trước khi sử dụng chúng.

Mảng có thể khai báo với kiểu interface hoặc lớp trừu tượng:

~~~~java
CharSequence[] messages = {
    "Hello",
    new StringBuilder("Welcome")
};
~~~~

Mỗi phần tử có thể là null hoặc một đối tượng thuộc kiểu tương thích với kiểu phần tử đã khai báo.

## 2. Truy cập, cập nhật và duyệt mảng một chiều

### 2.1. Chỉ số bắt đầu từ 0

Mảng Java đánh chỉ số từ 0. Nếu mảng có độ dài n, chỉ số hợp lệ nằm trong khoảng từ 0 đến n - 1:

~~~~java
int[] scores = {75, 82, 91, 68};

System.out.println(scores[0]); // 75
System.out.println(scores[3]); // 68

scores[1] = 88;
System.out.println(scores[1]); // 88
~~~~

Biểu thức truy cập phần tử có dạng **array[index]**. Kiểu của chỉ số là int sau khi áp dụng chuyển đổi số học đơn nguyên; chỉ số long không được chấp nhận. Nếu chỉ số âm hoặc lớn hơn hay bằng độ dài, JVM ném **ArrayIndexOutOfBoundsException** tại thời điểm chạy.

### 2.2. Duyệt bằng for

Vòng lặp for truyền thống phù hợp khi cần chỉ số, cập nhật theo vị trí hoặc duyệt một đoạn của mảng:

~~~~java
int[] scores = {75, 82, 91, 68};

for (int i = 0; i < scores.length; i++) {
    System.out.printf("scores[%d] = %d%n", i, scores[i]);
}
~~~~

Điều kiện thường dùng là **i < array.length**. Không dùng **i <= array.length**, vì chỉ số bằng length đã nằm ngoài mảng.

### 2.3. Duyệt bằng enhanced for

Khi chỉ cần đọc từng phần tử và không cần chỉ số, enhanced for giúp mã ngắn gọn:

~~~~java
int[] scores = {75, 82, 91, 68};
int total = 0;

for (int score : scores) {
    total += score;
}

double average = scores.length == 0
        ? 0.0
        : (double) total / scores.length;

System.out.println("Average: " + average);
~~~~

Biến vòng lặp nhận giá trị của từng phần tử. Với mảng kiểu nguyên thủy, thay đổi biến vòng lặp không cập nhật ngược lại phần tử trong mảng. Nếu cần thay đổi mảng, hãy dùng for với chỉ số hoặc một API nhận chỉ số.

### 2.4. Kiểm tra và xử lý mảng null, rỗng

Hai trạng thái này khác nhau:

- **null**: biến không tham chiếu đến đối tượng mảng nào.
- **Mảng rỗng**: đã có đối tượng mảng nhưng **length == 0**.

Trước khi truy cập length hoặc phần tử, có thể kiểm tra:

~~~~java
if (scores == null) {
    System.out.println("Array reference is null");
} else if (scores.length == 0) {
    System.out.println("Array has no elements");
} else {
    System.out.println("Number of scores: " + scores.length);
}
~~~~

Một API nhận mảng nên xác định rõ cách xử lý null: từ chối bằng NullPointerException hoặc chủ động chấp nhận null như trường hợp không có dữ liệu. Không nên để hành vi phụ thuộc vào một lần truy cập mảng tình cờ gây lỗi ở sâu bên trong chương trình.

## 3. Mảng nhiều chiều và mảng răng cưa

### 3.1. Bản chất của mảng nhiều chiều

Trong Java, mảng hai chiều là mảng mà mỗi phần tử có kiểu là mảng một chiều; mảng ba chiều là mảng chứa các mảng hai chiều, và cứ tiếp tục như vậy. Vì vậy, mảng nhiều chiều là các mảng lồng nhau, không phải một khối dữ liệu nhiều chiều bắt buộc có mọi hàng và cột bằng nhau.

Khai báo một số kiểu thường gặp:

~~~~java
int[][] matrix;
double[][][] cube;
String[][] table;
~~~~

Số cặp ngoặc vuông cho biết số cấp lồng nhau. Ví dụ, **int[][]** là mảng chứa các phần tử kiểu **int[]**; **int[][][]** là mảng chứa các phần tử kiểu **int[][]**.

### 3.2. Tạo ma trận có số hàng và cột cố định

Để tạo một ma trận 3 hàng, mỗi hàng có 4 cột:

~~~~java
int[][] matrix = new int[3][4];

matrix[0][0] = 10;
matrix[0][1] = 20;
matrix[1][2] = 30;
matrix[2][3] = 40;

System.out.println(matrix.length);       // 3 hàng
System.out.println(matrix[0].length);    // 4 cột ở hàng đầu tiên
System.out.println(matrix[1][2]);        // 30
~~~~

**matrix.length** là số hàng của mảng ngoài. **matrix[row].length** là số phần tử của hàng tương ứng. Với ma trận chữ nhật được tạo bằng **new int[3][4]**, các hàng đều có 4 phần tử.

Có thể khởi tạo trực tiếp dữ liệu:

~~~~java
int[][] matrix = {
    {1, 2, 3},
    {4, 5, 6},
    {7, 8, 9}
};
~~~~

Mỗi cặp dấu ngoặc nhọn bên trong khởi tạo một mảng con. Số phần tử của từng mảng con quyết định số cột thực tế của hàng đó.

### 3.3. Mảng răng cưa (jagged array)

Do mỗi hàng là một mảng riêng, các hàng có thể có độ dài khác nhau:

~~~~java
int[][] triangle = {
    {1},
    {2, 3},
    {4, 5, 6},
    {7, 8, 9, 10}
};

for (int row = 0; row < triangle.length; row++) {
    System.out.println(Arrays.toString(triangle[row]));
}
~~~~

Mảng như vậy được gọi là mảng răng cưa. Nó hữu ích khi mỗi nhóm dữ liệu có số phần tử khác nhau, ví dụ danh sách các môn học theo từng lớp, lịch làm việc theo ngày hoặc các dòng dữ liệu có độ dài không đồng nhất.

Có thể tạo mảng ngoài trước, rồi tạo từng hàng sau:

~~~~java
int[][] data = new int[3][];
data[0] = new int[2];
data[1] = new int[4];
data[2] = new int[1];

data[0][0] = 10;
data[1][3] = 40;
data[2][0] = 50;
~~~~

Ở đây chỉ mảng ngoài được tạo ban đầu. Các phần tử của nó là tham chiếu mảng con và có giá trị mặc định null cho đến khi được gán. Truy cập **data[0][0]** trước khi gán **data[0]** sẽ gây NullPointerException.

### 3.4. Duyệt mảng nhiều chiều an toàn

Với ma trận chữ nhật, có thể dùng hai vòng lặp for. Với mảng răng cưa, phải lấy độ dài của từng hàng:

~~~~java
int[][] values = {
    {10, 20},
    {30, 40, 50},
    {60}
};

for (int row = 0; row < values.length; row++) {
    for (int column = 0; column < values[row].length; column++) {
        System.out.printf("values[%d][%d] = %d%n",
                row, column, values[row][column]);
    }
}
~~~~

Nếu hàng có thể là null, hãy kiểm tra trước khi đọc length:

~~~~java
for (int[] row : values) {
    if (row == null) {
        continue;
    }

    for (int value : row) {
        System.out.println(value);
    }
}
~~~~

Không giả định **values[row].length** bằng **values[0].length** trừ khi chương trình đã bảo đảm ma trận có hình chữ nhật và mọi hàng đều khác null.

## 4. Những quy tắc kiểu dữ liệu quan trọng của mảng

### 4.1. Mảng kiểu tham chiếu có tính tương thích theo kiểu phần tử

Mảng kiểu tham chiếu có thể gán cho biến mảng của kiểu cha tương thích. Ví dụ:

~~~~java
class Animal {
}

class Dog extends Animal {
}

Animal[] animals = new Dog[2];
animals[0] = new Dog();
~~~~

Phép gán hợp lệ vì Dog là Animal. Tuy nhiên, đối tượng mảng thật vẫn có kiểu runtime là **Dog[]**. Nếu gán một Animal không phải Dog vào mảng này, JVM sẽ ném ArrayStoreException:

~~~~java
Animal[] animals = new Dog[2];
animals[0] = new Animal(); // ArrayStoreException khi chạy
~~~~

Đây là hệ quả của tính hiệp biến (covariance) của mảng tham chiếu và kiểm tra kiểu phần tử tại runtime. Không nên dựa vào biến kiểu mảng cha để lưu tùy ý các đối tượng thuộc lớp cha khi đối tượng mảng thật được tạo từ một mảng lớp con.

### 4.2. So sánh tham chiếu và so sánh nội dung

Toán tử **==** trên hai biến mảng kiểm tra chúng có tham chiếu đến cùng một đối tượng hay không. Nó không so sánh các phần tử:

~~~~java
int[] first = {1, 2, 3};
int[] second = {1, 2, 3};

System.out.println(first == second); // false
~~~~

Để so sánh nội dung mảng một chiều, dùng **Arrays.equals**:

~~~~java
System.out.println(Arrays.equals(first, second)); // true
~~~~

Với mảng nhiều chiều, cần hiểu sâu hơn về cách so sánh. **Arrays.equals** trên mảng ngoài chỉ so sánh các phần tử trực tiếp; nếu các phần tử đó lại là mảng con, phép so sánh mặc định giữa hai mảng con vẫn là so sánh tham chiếu. Dùng **Arrays.deepEquals** khi muốn so sánh đệ quy nội dung của các mảng lồng nhau:

~~~~java
int[][] left = {{1, 2}, {3, 4}};
int[][] right = {{1, 2}, {3, 4}};

System.out.println(Arrays.equals(left, right));     // false
System.out.println(Arrays.deepEquals(left, right)); // true
~~~~

Tương tự, dùng **Arrays.deepHashCode** khi cần mã băm dựa trên nội dung nhiều cấp; **Arrays.hashCode** phù hợp cho nội dung của một mảng ở cấp hiện tại. Khi triển khai equals và hashCode cho một lớp chứa mảng, cần chọn cặp phương thức nhất quán với cấu trúc dữ liệu của lớp.

### 4.3. Sao chép mảng là sao chép nông hay sâu?

Phép gán chỉ sao chép tham chiếu:

~~~~java
int[] source = {1, 2, 3};
int[] alias = source;

alias[0] = 99;
System.out.println(source[0]); // 99
~~~~

Để tạo mảng một chiều độc lập, có thể dùng **clone** hoặc **Arrays.copyOf**:

~~~~java
int[] source = {1, 2, 3};
int[] copy = Arrays.copyOf(source, source.length);

copy[0] = 99;
System.out.println(source[0]); // 1
~~~~

Với mảng nhiều chiều, **clone** hoặc **Arrays.copyOf** chỉ tạo mảng ngoài mới; các mảng con vẫn được dùng chung. Đây là sao chép nông (shallow copy):

~~~~java
int[][] source = {{1, 2}, {3, 4}};
int[][] shallowCopy = source.clone();

shallowCopy[0][0] = 99;
System.out.println(source[0][0]); // 99: hàng đầu tiên vẫn được chia sẻ
~~~~

Nếu cần bản sao độc lập cho mảng hai chiều gồm các hàng nguyên thủy, hãy sao chép từng hàng:

~~~~java
int[][] source = {{1, 2}, {3, 4}};
int[][] deepCopy = Arrays.stream(source)
        .map(row -> row == null ? null : Arrays.copyOf(row, row.length))
        .toArray(int[][]::new);

deepCopy[0][0] = 99;
System.out.println(source[0][0]); // 1
~~~~

Ví dụ này tạo một mảng ngoài mới và một mảng mới cho từng hàng khác null. Với mảng chứa đối tượng, sao chép từng hàng vẫn chỉ sao chép tham chiếu đến đối tượng; nếu cần đối tượng cũng độc lập, chương trình phải xác định và thực hiện chiến lược sao chép đối tượng phù hợp.

## 5. Lớp tiện ích java.util.Arrays

**Arrays** là lớp tiện ích có các phương thức static để thao tác với mảng. Import lớp khi sử dụng:

~~~~java
import java.util.Arrays;
~~~~

Các phương thức dưới đây được mô tả theo API Java SE 27. Phần lớn phương thức nhận mảng null sẽ ném NullPointerException, trừ các trường hợp API ghi rõ hành vi khác.

### 5.1. Chuyển nội dung mảng thành chuỗi để hiển thị

Không nên dùng phép nối chuỗi trực tiếp với biến mảng để xem nội dung, vì kết quả thường là thông tin định danh đối tượng. Dùng **Arrays.toString** cho mảng một chiều:

~~~~java
int[] scores = {75, 82, 91};
System.out.println(Arrays.toString(scores)); // [75, 82, 91]
~~~~

Với mảng nhiều chiều, **Arrays.deepToString** hiển thị nội dung lồng nhau:

~~~~java
int[][] matrix = {
    {1, 2, 3},
    {4, 5, 6}
};

System.out.println(Arrays.deepToString(matrix));
// [[1, 2, 3], [4, 5, 6]]
~~~~

**Arrays.toString(Object[])** không tự đi sâu vào các mảng con; hãy dùng deepToString để đọc cấu trúc nhiều chiều. Các phương thức này hữu ích khi ghi log hoặc gỡ lỗi, nhưng không phải định dạng serialization ổn định để lưu dữ liệu lâu dài.

### 5.2. Điền giá trị bằng fill

**Arrays.fill** gán cùng một giá trị cho mọi phần tử hoặc một đoạn của mảng. Đoạn chỉ số có điểm bắt đầu inclusive và điểm kết thúc exclusive:

~~~~java
int[] seats = new int[8];
Arrays.fill(seats, 1);
System.out.println(Arrays.toString(seats));
// [1, 1, 1, 1, 1, 1, 1, 1]

Arrays.fill(seats, 2, 5, 0);
System.out.println(Arrays.toString(seats));
// [1, 1, 0, 0, 0, 1, 1, 1]
~~~~

Với mảng tham chiếu, fill ghi cùng một tham chiếu vào mọi vị trí:

~~~~java
StringBuilder shared = new StringBuilder("start");
StringBuilder[] buffers = new StringBuilder[3];
Arrays.fill(buffers, shared);
~~~~

Ba phần tử trên cùng tham chiếu đến một StringBuilder. Nếu thay đổi đối tượng qua một phần tử, khi đọc qua phần tử khác cũng thấy thay đổi. Nếu muốn mỗi vị trí có một đối tượng riêng, hãy tạo đối tượng riêng cho từng vị trí bằng vòng lặp hoặc **Arrays.setAll**.

### 5.3. Tạo hoặc cập nhật phần tử bằng setAll

**Arrays.setAll** nhận một hàm tạo giá trị từ chỉ số. Phương thức này phù hợp khi giá trị của phần tử phụ thuộc vào vị trí:

~~~~java
int[] squares = new int[6];
Arrays.setAll(squares, index -> index * index);

System.out.println(Arrays.toString(squares));
// [0, 1, 4, 9, 16, 25]

StringBuilder[] buffers = new StringBuilder[3];
Arrays.setAll(buffers, index -> new StringBuilder("slot-" + index));
~~~~

Có overload cho mảng nguyên thủy int, long, double và mảng tham chiếu. **Arrays.parallelSetAll** thực hiện phép gán theo hướng song song. Chỉ dùng dạng song song khi hàm tạo giá trị độc lập theo chỉ số, không dựa vào thứ tự thực thi và không ghi vào trạng thái dùng chung không được đồng bộ. Với mảng nhỏ, vòng lặp hoặc setAll thường dễ hiểu hơn; song song không mặc nhiên nhanh hơn.

### 5.4. Sắp xếp bằng sort

**Arrays.sort** sắp xếp trực tiếp mảng được truyền vào:

~~~~java
int[] scores = {91, 75, 82, 68};
Arrays.sort(scores);
System.out.println(Arrays.toString(scores));
// [68, 75, 82, 91]
~~~~

Với mảng đối tượng, có thể dùng thứ tự tự nhiên của phần tử hoặc cung cấp Comparator:

~~~~java
import java.util.Arrays;
import java.util.Comparator;

String[] names = {"Minh", "An", "Binh", "Lan"};

Arrays.sort(names);
System.out.println(Arrays.toString(names));
// [An, Binh, Lan, Minh]

Arrays.sort(names, Comparator.comparingInt(String::length));
System.out.println(Arrays.toString(names));
~~~~

Sắp xếp theo Comparator cho phép định nghĩa thứ tự theo nhiều thuộc tính:

~~~~java
import java.util.Arrays;
import java.util.Comparator;

record Student(String name, int score) {}

class StudentSortingDemo {
    public static void main(String[] args) {
        Student[] students = {
            new Student("Lan", 85),
            new Student("An", 92),
            new Student("Minh", 85)
        };

        Arrays.sort(students,
                Comparator.comparingInt(Student::score).reversed()
                        .thenComparing(Student::name));
    }
}
~~~~

Đoạn mã trên xếp điểm giảm dần, sau đó tên tăng dần. Các phần tử của vùng được sắp xếp phải có thể so sánh theo Comparable hoặc Comparator tương ứng. Sắp xếp mảng đối tượng bằng Arrays.sort là ổn định: các phần tử có thứ tự so sánh bằng nhau giữ nguyên thứ tự tương đối trước đó.

Có thể sắp xếp một đoạn từ **fromIndex** đến trước **toIndex**:

~~~~java
int[] values = {9, 5, 8, 2, 7, 1};
Arrays.sort(values, 1, 5);
System.out.println(Arrays.toString(values));
// [9, 2, 5, 7, 8, 1]
~~~~

### 5.5. Sắp xếp song song bằng parallelSort

**Arrays.parallelSort** có overload cho các kiểu nguyên thủy và mảng đối tượng. API chia công việc sắp xếp thành các phần có thể xử lý song song, sau đó ghép kết quả. Với mảng nhỏ, phương thức có thể chuyển sang cách sắp xếp tuần tự; chi phí điều phối song song có thể lớn hơn lợi ích.

~~~~java
int[] values = {9, 5, 8, 2, 7, 1};
Arrays.parallelSort(values);
System.out.println(Arrays.toString(values));
// [1, 2, 5, 7, 8, 9]
~~~~

Không nên thay tất cả lệnh sort bằng parallelSort theo thói quen. Hãy đo hiệu năng trên kích thước dữ liệu và tải thực tế của ứng dụng; parallelSort sử dụng ForkJoin common pool và có thể cạnh tranh tài nguyên với các tác vụ song song khác.

### 5.6. Tìm kiếm bằng binarySearch

**Arrays.binarySearch** tìm một giá trị trong mảng đã được sắp xếp theo đúng thứ tự tìm kiếm. Nếu mảng chưa được sắp xếp hoặc được sắp xếp theo một Comparator khác với Comparator dùng để tìm, kết quả không được bảo đảm.

~~~~java
int[] values = {10, 20, 30, 40, 50};

int foundIndex = Arrays.binarySearch(values, 30);
System.out.println(foundIndex); // 2

int missingIndex = Arrays.binarySearch(values, 35);
System.out.println(missingIndex); // -4
~~~~

Khi không tìm thấy, phương thức trả về một số âm theo công thức **-(insertionPoint) - 1**. Insertion point là vị trí mà khóa cần tìm có thể được chèn vào để giữ nguyên thứ tự tăng dần. Trong ví dụ, 35 sẽ được chèn tại chỉ số 3, nên kết quả là -4.

Với mảng đối tượng có Comparator:

~~~~java
import java.util.Arrays;
import java.util.Comparator;

String[] names = {"An", "Binh", "Lan", "Minh"};
int index = Arrays.binarySearch(names, "Lan", Comparator.naturalOrder());
~~~~

Nếu sắp xếp bằng Comparator riêng, phải truyền cùng quy tắc so sánh khi tìm kiếm. Với dữ liệu chưa sắp xếp, dùng vòng lặp tuyến tính hoặc sắp xếp trước khi tìm kiếm nhị phân.

### 5.7. Sao chép bằng copyOf và copyOfRange

**Arrays.copyOf** tạo mảng mới với độ dài chỉ định. Nếu độ dài mới nhỏ hơn, dữ liệu cuối bị cắt; nếu lớn hơn, các vị trí thêm vào nhận giá trị mặc định của kiểu phần tử:

~~~~java
int[] original = {10, 20, 30};

int[] longer = Arrays.copyOf(original, 5);
System.out.println(Arrays.toString(longer));
// [10, 20, 30, 0, 0]

int[] shorter = Arrays.copyOf(original, 2);
System.out.println(Arrays.toString(shorter));
// [10, 20]
~~~~

**Arrays.copyOfRange** sao chép một đoạn có điểm bắt đầu inclusive và điểm kết thúc exclusive:

~~~~java
int[] original = {10, 20, 30, 40, 50};
int[] middle = Arrays.copyOfRange(original, 1, 4);

System.out.println(Arrays.toString(middle));
// [20, 30, 40]
~~~~

Với mảng đối tượng, các phương thức này sao chép tham chiếu phần tử, không tự sao chép sâu đối tượng. Với mảng nhiều chiều, chúng cũng chỉ sao chép các tham chiếu đến mảng con.

### 5.8. So sánh nội dung bằng equals và deepEquals

| Phương thức | Mục đích |
| --- | --- |
| Arrays.equals(a, b) | So sánh độ dài và từng phần tử ở cấp hiện tại |
| Arrays.deepEquals(a, b) | So sánh đệ quy nội dung của các mảng lồng nhau |
| Arrays.hashCode(a) | Tạo mã băm dựa trên các phần tử ở cấp hiện tại |
| Arrays.deepHashCode(a) | Tạo mã băm dựa trên nội dung lồng nhau |

Ví dụ:

~~~~java
int[][] first = {{1, 2}, {3, 4}};
int[][] second = {{1, 2}, {3, 4}};

System.out.println(Arrays.equals(first, second));     // false
System.out.println(Arrays.deepEquals(first, second)); // true
System.out.println(Arrays.deepHashCode(first)
        == Arrays.deepHashCode(second));               // true
~~~~

Không dùng mã băm để kết luận hai mảng bằng nhau. Hai giá trị có thể có cùng hash code mà nội dung khác nhau; hãy dùng equals hoặc deepEquals để xác định tính bằng nhau.

### 5.9. So sánh thứ tự và tìm vị trí khác biệt

Java SE cung cấp **Arrays.compare** và **Arrays.mismatch** để so sánh mảng:

- **compare** so sánh từ điển (lexicographical). Kết quả âm nếu mảng thứ nhất đứng trước, bằng 0 nếu bằng nhau theo quy tắc so sánh, dương nếu đứng sau.
- **mismatch** trả về chỉ số đầu tiên mà hai mảng khác nhau; trả về -1 nếu không có khác biệt.

~~~~java
int[] a = {1, 3, 5, 7};
int[] b = {1, 3, 6, 7};

System.out.println(Arrays.compare(a, b));  // Số âm
System.out.println(Arrays.mismatch(a, b)); // 2
~~~~

Các overload theo đoạn cũng dùng điểm cuối exclusive. Với mảng đối tượng, có thể truyền Comparator để định nghĩa phép so sánh. Những phương thức này hữu ích khi kiểm tra phiên bản dữ liệu, so sánh kết quả xử lý hoặc tìm phần tử đầu tiên khiến hai dãy khác nhau.

### 5.10. Tính tổng lũy kế bằng parallelPrefix

**Arrays.parallelPrefix** thay đổi mảng tại chỗ bằng cách tính giá trị tích lũy từ trái sang phải. Ví dụ dùng phép cộng:

~~~~java
int[] values = {2, 1, 0, 3};
Arrays.parallelPrefix(values, Integer::sum);

System.out.println(Arrays.toString(values));
// [2, 3, 3, 6]
~~~~

Phép toán được truyền vào phải có tính kết hợp (associative) và không tạo tác dụng phụ, vì các phần có thể được tính song song. Với số thực dấu phẩy động, phép cộng không hoàn toàn có tính kết hợp do sai số làm tròn, nên kết quả có thể khác cách cộng tuần tự. Hãy chọn phép toán phù hợp với yêu cầu chính xác của dữ liệu.

### 5.11. Chuyển mảng thành Stream

**Arrays.stream** tạo Stream từ mảng đối tượng và các primitive stream tương ứng cho int, long, double:

~~~~java
int[] scores = {75, 82, 91, 68, 82};

int total = Arrays.stream(scores).sum();
double average = Arrays.stream(scores).average().orElse(0.0);
long passed = Arrays.stream(scores).filter(score -> score >= 80).count();

System.out.println(total);
System.out.println(average);
System.out.println(passed);
~~~~

Với mảng đối tượng:

~~~~java
import java.util.List;

String[] names = {"An", "Binh", "Lan", "Minh"};

List<String> longNames = Arrays.stream(names)
        .filter(name -> name.length() >= 4)
        .toList();
~~~~

Stream phù hợp với các phép lọc, biến đổi, tổng hợp và pipeline dữ liệu. Nếu cần cập nhật trực tiếp phần tử theo chỉ số, vòng lặp hoặc setAll thường rõ ràng hơn.

### 5.12. Chuyển mảng đối tượng thành List bằng asList

**Arrays.asList** tạo một List có kích thước cố định và được hỗ trợ bởi mảng gốc:

~~~~java
String[] names = {"An", "Binh", "Lan"};
List<String> view = Arrays.asList(names);

view.set(1, "Bao");
System.out.println(names[1]); // Bao
~~~~

Có thể thay phần tử bằng **set**, và thay đổi qua mảng cũng được nhìn thấy qua List. Tuy nhiên, các thao tác làm thay đổi kích thước như **add** hoặc **remove** không được hỗ trợ và sẽ ném UnsupportedOperationException.

Lưu ý với mảng kiểu nguyên thủy:

~~~~java
int[] numbers = {1, 2, 3};
List<int[]> oneElementList = Arrays.asList(numbers);
~~~~

Do phương thức nhận tham số varargs kiểu tham chiếu, mảng int được truyền như một đối tượng duy nhất; kết quả là List có một phần tử kiểu int[], không phải List<Integer> gồm ba phần tử. Nếu cần List<Integer>, có thể dùng:

~~~~java
List<Integer> boxedNumbers = Arrays.stream(numbers)
        .boxed()
        .toList();
~~~~

**Stream.toList()** trả về List không sửa đổi được. Nếu cần List có thể thêm hoặc xóa phần tử, hãy tạo một ArrayList mới từ dữ liệu đã chuyển đổi.

## 6. Ví dụ tổng hợp: xử lý điểm và ma trận dữ liệu

Ví dụ sau kết hợp mảng một chiều, mảng nhiều chiều và các phương thức Arrays thường dùng:

~~~~java
import java.util.Arrays;
import java.util.Comparator;

public class ArrayOperationsDemo {
    public static void main(String[] args) {
        int[] scores = {82, 75, 91, 68, 82};

        // Sắp xếp mảng tại chỗ.
        Arrays.sort(scores);
        System.out.println("Sorted: " + Arrays.toString(scores));

        // Tìm kiếm nhị phân trên mảng đã sắp xếp.
        int index = Arrays.binarySearch(scores, 82);
        System.out.println("Index of 82: " + index);

        // Tạo bản sao độc lập và điền các vị trí mới.
        int[] expanded = Arrays.copyOf(scores, scores.length + 2);
        Arrays.fill(expanded, scores.length, expanded.length, 0);
        System.out.println("Expanded: " + Arrays.toString(expanded));

        // Tính tổng lũy kế.
        int[] cumulative = {10, 20, 15, 5};
        Arrays.parallelPrefix(cumulative, Integer::sum);
        System.out.println("Cumulative: " + Arrays.toString(cumulative));

        // Mảng nhiều chiều với các hàng có độ dài khác nhau.
        int[][] monthlySales = {
            {120, 150, 130},
            {90, 110},
            {200, 180, 210, 190}
        };

        System.out.println("Sales: " + Arrays.deepToString(monthlySales));

        int totalSales = 0;
        for (int[] month : monthlySales) {
            if (month == null) {
                continue;
            }
            for (int value : month) {
                totalSales += value;
            }
        }
        System.out.println("Total sales: " + totalSales);

        // Sắp xếp mảng đối tượng theo độ dài tên rồi theo tên.
        String[] names = {"Minh", "An", "Binh", "Lan"};
        Arrays.sort(names,
                Comparator.comparingInt(String::length)
                        .thenComparing(Comparator.naturalOrder()));
        System.out.println("Names: " + Arrays.toString(names));

        // Tạo Stream từ mảng số nguyên để tính trung bình.
        double average = Arrays.stream(scores).average().orElse(0.0);
        System.out.println("Average score: " + average);
    }
}
~~~~

Trong ví dụ:

1. sort thay đổi thứ tự phần tử trong mảng scores.
2. binarySearch chỉ được gọi sau khi scores đã được sắp xếp.
3. copyOf tạo mảng mới, còn fill cập nhật một đoạn có điểm cuối không bao gồm.
4. parallelPrefix cập nhật trực tiếp mảng cumulative.
5. monthlySales là mảng răng cưa; vòng lặp lấy độ dài riêng của từng hàng.
6. Comparator xác định thứ tự sắp xếp của mảng String.
7. Arrays.stream tạo IntStream để tính trung bình.

## 7. Lỗi thường gặp và cách xử lý

| Tình huống | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| ArrayIndexOutOfBoundsException | Chỉ số âm hoặc bằng/lớn hơn length | Kiểm tra giới hạn vòng lặp và chỉ số trước khi truy cập |
| NullPointerException khi đọc mảng nhiều chiều | Mảng ngoài đã tạo nhưng một hàng chưa được khởi tạo | Tạo mảng con trước khi truy cập hoặc kiểm tra hàng null |
| ArrayStoreException | Gán đối tượng không đúng kiểu runtime của mảng tham chiếu | Bảo đảm đối tượng gán tương thích với kiểu phần tử thực tế |
| In kết quả dạng mã định danh như [I@... | Nối chuỗi trực tiếp với mảng | Dùng Arrays.toString hoặc Arrays.deepToString |
| Hai mảng có dữ liệu giống nhau nhưng == trả false | == so sánh tham chiếu, không so sánh nội dung | Dùng Arrays.equals hoặc Arrays.deepEquals |
| Arrays.equals cho mảng hai chiều trả false ngoài dự kiến | Phần tử trực tiếp là các mảng con, phép so sánh chỉ ở cấp hiện tại | Dùng Arrays.deepEquals và deepHashCode |
| binarySearch trả kết quả âm | Không tìm thấy khóa; kết quả mã hóa insertion point | Kiểm tra kết quả >= 0 trước khi xem là chỉ số; hoặc giải mã vị trí chèn |
| binarySearch cho kết quả không mong đợi | Mảng chưa sắp xếp hoặc dùng Comparator không giống lúc sắp xếp | Sắp xếp và tìm kiếm bằng cùng thứ tự |
| asList không cho add/remove | List view có kích thước cố định và gắn với mảng | Tạo ArrayList mới nếu cần thay đổi kích thước |
| Arrays.asList(intArray) chỉ có một phần tử | Mảng nguyên thủy được truyền như một đối tượng vào varargs | Dùng Arrays.stream(intArray).boxed().toList() |
| Thay đổi bản sao hai chiều làm đổi dữ liệu gốc | copyOf hoặc clone chỉ sao chép mảng ngoài | Sao chép từng hàng; với đối tượng cần chiến lược sao chép sâu riêng |

Khi xử lý lỗi truy cập mảng, hãy kiểm tra cả giá trị chỉ số và trạng thái tham chiếu của từng cấp. Trong mảng nhiều chiều, một chỉ số hàng hợp lệ không bảo đảm hàng đó đã được khởi tạo hoặc chỉ số cột hợp lệ.

## 8. Khi nào nên dùng mảng?

Mảng phù hợp khi:

- Số phần tử được xác định trước hoặc thay đổi không thường xuyên.
- Cần truy cập phần tử trực tiếp bằng chỉ số.
- Cần lưu dữ liệu kiểu nguyên thủy mà không phải đóng gói từng giá trị thành đối tượng.
- Cần truyền dữ liệu đến API, thư viện hoặc giao diện tương tác yêu cầu kiểu mảng.
- Cấu trúc dữ liệu có dạng hàng/cột hoặc các nhóm con với kích thước đã biết.

Nếu kích thước cần tăng giảm thường xuyên, có thao tác thêm/xóa phần tử ở nhiều vị trí hoặc cần nhiều tiện ích của Collections Framework, hãy cân nhắc một cấu trúc Collection phù hợp. Mảng vẫn hữu ích làm biểu diễn dữ liệu nền, còn Collection cung cấp giao diện thao tác linh hoạt hơn khi yêu cầu của ứng dụng cần điều đó.

Không nên chọn mảng nhiều chiều chỉ vì dữ liệu được trình bày dưới dạng bảng. Cần xác định dữ liệu có thật sự cần các hàng có cùng số cột hay không. Nếu độ dài mỗi hàng khác nhau, mô hình mảng răng cưa phản ánh đúng cấu trúc. Nếu cần một ma trận chữ nhật, hãy kiểm tra kích thước hàng khi nhận dữ liệu từ nguồn bên ngoài.

## 9. Tổng kết API Arrays cần nhớ

| Nhu cầu | Phương thức |
| --- | --- |
| In mảng một chiều | Arrays.toString |
| In mảng nhiều chiều | Arrays.deepToString |
| Điền một giá trị | Arrays.fill |
| Tạo giá trị theo chỉ số | Arrays.setAll |
| Sắp xếp tăng dần hoặc theo Comparator | Arrays.sort |
| Sắp xếp song song cho dữ liệu phù hợp | Arrays.parallelSort |
| Tìm kiếm trong mảng đã sắp xếp | Arrays.binarySearch |
| Sao chép hoặc đổi độ dài | Arrays.copyOf |
| Sao chép một đoạn | Arrays.copyOfRange |
| So sánh nội dung một cấp | Arrays.equals |
| So sánh nội dung mảng lồng nhau | Arrays.deepEquals |
| So sánh thứ tự từ điển | Arrays.compare |
| Tìm vị trí khác biệt đầu tiên | Arrays.mismatch |
| Tính tổng lũy kế | Arrays.parallelPrefix |
| Tạo Stream từ mảng | Arrays.stream |
| Tạo List view cố định kích thước | Arrays.asList |

Hiểu rõ mảng là đối tượng có độ dài cố định, cách mảng nhiều chiều được tạo từ các mảng con, và sự khác nhau giữa sao chép nông với sao chép sâu sẽ giúp tránh phần lớn lỗi khi xử lý dữ liệu. Kết hợp các phương thức trong Arrays với vòng lặp, Comparator và Stream giúp chương trình ngắn gọn, dễ đọc và bám sát API Java hiện hành.
