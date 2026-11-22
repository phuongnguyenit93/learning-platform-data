# Collection là gì và bài toán quản lý nhóm đối tượng

Một chương trình thường phải làm việc với **một nhóm dữ liệu có liên quan**: danh sách công việc, giỏ hàng, người tham gia một sự kiện hoặc các yêu cầu đang chờ xử lý. Khi số lượng phần tử thay đổi, chương trình cần cách thêm, tìm, xóa, đếm và duyệt cả nhóm mà vẫn giữ được quy tắc dữ liệu mong muốn.

Trong Java, **collection** là cách biểu diễn một nhóm phần tử thành một đối tượng để quản lý và thao tác. Giao diện `Collection<E>` cung cấp hợp đồng chung cho nhiều kiểu tập hợp; những kiểu như `List`, `Set` và `Queue` bổ sung quy tắc sử dụng cụ thể.

Sau bài này, bạn có thể:

- Giải thích collection giải quyết bài toán gì.
- Phân biệt `Collection`, Java Collections Framework và `Collections`.
- Sử dụng các thao tác quản lý nhóm đối tượng trong một chương trình nhỏ.
- Đặt câu hỏi về thứ tự, trùng lặp và cách truy cập trước khi chọn kiểu tập hợp.

Các chương trình hoàn chỉnh trong bài dùng API có sẵn từ Java 17. Chúng đã được biên dịch với `--release 17` và chạy để kiểm tra kết quả.

## 1. Từ một đối tượng đến một nhóm đối tượng

Giả sử bạn viết ứng dụng quản lý công việc. Một biến có thể giữ một công việc:

```java
String task = "Đọc đề";
```

Đây là đoạn minh họa có thể đặt trong một phương thức. Khi có nhiều công việc, việc tạo các biến `task1`, `task2`, `task3` sẽ gây khó khăn:

- Số công việc thực tế chỉ biết khi chương trình chạy.
- Muốn tìm một công việc phải tự kiểm tra từng biến.
- Muốn xử lý tất cả công việc phải lặp lại các câu lệnh.
- Xóa một công việc khiến việc theo dõi các biến còn lại trở nên rối.
- Mỗi phần của chương trình có thể tự đặt ra một cách quản lý khác nhau.

Ta cần biểu diễn **cả nhóm** bằng một biến, rồi thao tác theo mục đích:

| Nhu cầu của chương trình | Thao tác mong muốn |
| --- | --- |
| Người dùng tạo công việc | Thêm phần tử |
| Người dùng tìm công việc đã có | Kiểm tra sự tồn tại |
| Người dùng bỏ một công việc | Xóa phần tử |
| Hiển thị số công việc hiện tại | Đếm phần tử |
| Hiển thị các công việc | Duyệt từng phần tử |
| Bắt đầu lại danh sách | Xóa toàn bộ phần tử |

Đây là bài toán quản lý nhóm đối tượng. Collection cung cấp mô hình dữ liệu và những thao tác có thể tái sử dụng cho bài toán đó.

### Quản lý nhóm còn bao gồm quy tắc của nhóm

Cùng có đầu vào `Lan, Minh, Lan`, hai yêu cầu sau sẽ cho kết quả khác nhau:

- **Lưu lượt đăng ký:** có ba lượt; hai lượt mang tên Lan vẫn phải được giữ.
- **Lưu người tham gia duy nhất:** nếu tên được dùng làm định danh trong ví dụ đơn giản này, chỉ còn hai người.

Vì vậy, chọn collection không chỉ là tìm một chỗ chứa được nhiều phần tử. Bạn còn phải quyết định phần tử có được trùng không, thứ tự có ý nghĩa không và phần tử sẽ được truy cập như thế nào.

Trong hệ thống thực tế, định danh người tham gia nên là một giá trị ổn định như mã người dùng; tên hiển thị có thể trùng.

## 2. Phân biệt các tên dễ nhầm

| Tên | Ý nghĩa |
| --- | --- |
| collection | Khái niệm một nhóm phần tử được quản lý cùng nhau |
| `Collection<E>` | Giao diện trong `java.util`, khai báo các thao tác chung cho nhiều kiểu tập hợp |
| Java Collections Framework | Hệ thống giao diện, lớp triển khai và công cụ phục vụ việc lưu trữ, thao tác trên nhóm dữ liệu |
| `Collections` | Lớp tiện ích trong `java.util`, cung cấp các phương thức tĩnh làm việc với collection |

Cách viết hoa có ý nghĩa. `Collection` là một giao diện; `Collections` là một lớp khác. Tên “Collections Framework” chỉ phạm vi rộng hơn một giao diện đơn lẻ.

Ký hiệu `E` trong `Collection<E>` đại diện cho kiểu phần tử. Ví dụ, `Collection<String>` biểu diễn một collection có các phần tử thuộc kiểu `String`.

### Collection và Map

`Map<K, V>` lưu quan hệ **khóa → giá trị**, chẳng hạn `mã công việc → thông tin công việc`. `Map` thuộc Java Collections Framework nhưng **không kế thừa `Collection`**.

Sự phân biệt này ảnh hưởng đến cách thiết kế:

- Nếu cần quản lý một nhóm công việc, hãy xét các kiểu collection.
- Nếu thường xuyên cần tìm công việc theo mã riêng, hãy xét mô hình khóa–giá trị của `Map`.

Một số góc nhìn dữ liệu của map có thể được biểu diễn bằng collection, nhưng điều đó không làm bản thân `Map` trở thành `Collection`.

## 3. Mảng giải quyết được gì?

Mảng cũng lưu nhiều phần tử và rất hữu ích khi số vị trí đã xác định. Tuy nhiên, độ dài của **một đối tượng mảng** không thay đổi sau khi được tạo.

Ví dụ minh họa trong một phương thức:

```java
String[] tasks = new String[3];
int used = 0;

tasks[used++] = "Đọc đề";
tasks[used++] = "Viết mã";
```

Ở thời điểm này:

- `tasks.length` là `3`: số vị trí của mảng.
- `used` là `2`: số công việc mà chương trình đang quản lý.
- Vị trí chưa được gán còn giữ giá trị mặc định `null`.

Nếu muốn thêm nhiều hơn ba công việc, bạn phải tạo mảng khác và chuyển dữ liệu. Nếu muốn xóa ở giữa, bạn phải tự quyết định có dồn phần tử và cập nhật `used` hay không.

Một lớp như `ArrayList` đóng gói phần việc quản lý cấu trúc lưu trữ đó. Chương trình có thể tập trung vào “thêm công việc” thay vì tự quản lý chỗ trống trong mảng.

| Đặc điểm | Mảng | Collection, tùy kiểu triển khai |
| --- | --- | --- |
| Số phần tử đang quản lý | Thường phải tự theo dõi nếu chỉ dùng một phần mảng | Hỏi qua `size()` |
| Khả năng thay đổi số phần tử | Cần tự tổ chức trên mảng hiện có hoặc thay mảng | Có thể được lớp triển khai hỗ trợ |
| Thêm, tìm, xóa theo đối tượng | Tự viết logic hoặc dùng công cụ phù hợp | Có hợp đồng thao tác chung |
| Kiểu phần tử | Hỗ trợ kiểu nguyên thủy và kiểu tham chiếu | Tham số kiểu dùng kiểu tham chiếu |
| Quy tắc thứ tự, trùng lặp | Theo cấu trúc mảng và logic tự viết | Phụ thuộc loại collection |

Không phải collection nào cũng cho phép thêm hoặc xóa. Ví dụ, danh sách tạo bởi `List.of(...)` không cho phép thay đổi cấu trúc. Cần đọc hợp đồng của đối tượng cụ thể thay vì suy ra “collection nào cũng tự tăng giảm được”.

Mảng vẫn là lựa chọn phù hợp khi mô hình dữ liệu cần số vị trí cố định hoặc cần lưu trực tiếp giá trị nguyên thủy. Collection có thêm chi phí và các quy tắc riêng; việc lựa chọn nên xuất phát từ bài toán.

## 4. Giao diện, lớp triển khai và phần tử

Xét khai báo:

```java
Collection<String> tasks = new ArrayList<>();
```

Có ba ý cần đọc được:

1. **`Collection<String>`** là kiểu của biến: phần chương trình sử dụng biến này dựa vào hợp đồng quản lý các phần tử `String`.
2. **`new ArrayList<>()`** tạo đối tượng thực tế: lớp `ArrayList` quyết định cách lưu trữ và những đặc tính cụ thể.
3. **`tasks`** giữ tham chiếu đến đối tượng collection; đối tượng đó quản lý các phần tử được thêm vào.

Không thể tạo đối tượng trực tiếp bằng `new Collection<>()` vì `Collection` là giao diện.

Khai báo theo giao diện giúp đoạn mã chỉ phụ thuộc vào những khả năng nó cần. Tuy nhiên, việc đổi lớp triển khai vẫn phải kiểm tra lại ý nghĩa dữ liệu: thay một danh sách cho phép trùng bằng một tập hợp loại trùng có thể làm thay đổi kết quả nghiệp vụ.

### Các nhóm giao diện thường gặp

| Nhóm | Câu hỏi dẫn tới lựa chọn |
| --- | --- |
| `Collection<E>` | Đoạn mã chỉ cần những thao tác chung như thêm, đếm, tìm hoặc duyệt? |
| `List<E>` | Có cần một chuỗi phần tử có thứ tự, truy cập theo chỉ số và thường cho phép trùng? |
| `Set<E>` | Có cần bảo đảm không trùng theo quy tắc của tập hợp? |
| `Queue<E>` | Có cần nhận và xử lý phần tử theo chính sách hàng đợi? |
| `Deque<E>` | Có cần thao tác ở cả hai đầu của nhóm? |
| `Map<K, V>` | Có cần liên kết và tra cứu giá trị theo khóa? |

`List`, `Set` và `Queue` nằm trong hệ thống kiểu của `Collection`; `Deque` mở rộng `Queue`. Bảng thể hiện vai trò chính, không liệt kê toàn bộ cây kế thừa của từng phiên bản Java.

Một `Queue` không nhất thiết luôn tuân theo thứ tự vào trước ra trước; chẳng hạn, hàng đợi ưu tiên có chính sách chọn phần tử riêng. Tương tự, giao diện `Collection` không hứa rằng mọi lớp triển khai đều có thứ tự duyệt giống nhau.

### Chỉ yêu cầu khả năng thực sự cần dùng

Nếu một phương thức chỉ duyệt các phần tử, nó không cần yêu cầu riêng `ArrayList`. Nếu một phương thức cần lấy phần tử bằng chỉ số, `Collection` chưa đủ vì giao diện này không khai báo `get(int)`; khi đó cần xem hợp đồng `List`.

`Collection` mở rộng `Iterable`, nên có thể được duyệt bằng vòng lặp for-each.

## 5. Chương trình hoàn chỉnh: quản lý công việc

Tạo tệp **`CollectionIntroDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;

public class CollectionIntroDemo {
    public static void main(String[] args) {
        Collection<String> tasks = new ArrayList<>();

        System.out.println("Ban đầu: " + tasks.size());

        tasks.add("Đọc đề");
        tasks.add("Viết mã");
        tasks.add("Kiểm thử");
        tasks.add("Viết mã");

        System.out.println("Sau khi thêm: " + tasks.size());
        System.out.println("Có Kiểm thử: " + tasks.contains("Kiểm thử"));
        System.out.println("Xóa Viết mã: " + tasks.remove("Viết mã"));
        System.out.println("Xóa Triển khai: " + tasks.remove("Triển khai"));
        System.out.println("Còn lại: " + tasks.size());

        for (String task : tasks) {
            System.out.println("- " + task);
        }

        tasks.clear();
        System.out.println("Sau clear, rỗng: " + tasks.isEmpty());
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```text
javac -encoding UTF-8 --release 17 CollectionIntroDemo.java
java -Dfile.encoding=UTF-8 CollectionIntroDemo
```

Kết quả stdout:

```text
Ban đầu: 0
Sau khi thêm: 4
Có Kiểm thử: true
Xóa Viết mã: true
Xóa Triển khai: false
Còn lại: 3
- Đọc đề
- Kiểm thử
- Viết mã
Sau clear, rỗng: true
```

### Đọc diễn biến của chương trình

1. Collection mới chưa có phần tử nên `size()` trả về `0`.
2. Bốn lần `add` tạo bốn phần tử. `ArrayList` cho phép trùng nên hai chuỗi `"Viết mã"` cùng tồn tại.
3. `contains("Kiểm thử")` kiểm tra sự tồn tại và trả về `true`.
4. `remove("Viết mã")` trên danh sách này xóa **một lần xuất hiện đầu tiên**, trả về `true`; một phần tử `"Viết mã"` vẫn còn.
5. `remove("Triển khai")` không tìm thấy phần tử để xóa nên trả về `false`.
6. Vòng lặp for-each duyệt ba phần tử còn lại theo thứ tự của `ArrayList`.
7. `clear()` loại bỏ toàn bộ phần tử khỏi collection, nên `isEmpty()` trả về `true`.

Biến có kiểu `Collection<String>`, nhưng kết quả về thứ tự và phần tử trùng trong ví dụ đến từ đối tượng `ArrayList` thực tế.

### Các thao tác vừa sử dụng

| Thao tác | Ý nghĩa trong ví dụ |
| --- | --- |
| `add(element)` | Thêm một phần tử |
| `size()` | Lấy số phần tử hiện có |
| `contains(element)` | Kiểm tra có phần tử phù hợp hay không |
| `remove(element)` | Xóa một phần tử phù hợp nếu có |
| `isEmpty()` | Kiểm tra collection không chứa phần tử nào |
| `clear()` | Loại bỏ toàn bộ phần tử |
| for-each | Lần lượt xử lý các phần tử |

Đây là hợp đồng sử dụng, không phải cam kết rằng mọi lớp đều hỗ trợ sửa đổi hay có cùng chi phí thực thi.

Với chuỗi trong ví dụ, việc so khớp giá trị dựa trên quy tắc `equals` của `String`. Khi dùng đối tượng tự định nghĩa, bạn cần thiết kế quy tắc bằng nhau phù hợp; đặc biệt, các tập hợp dùng bảng băm còn phụ thuộc sự nhất quán giữa `equals` và `hashCode`.

## 6. Cùng hợp đồng, khác quy tắc nhóm

Chương trình sau dùng một phương thức nhận `Collection<String>` để hiển thị hai nhóm có quy tắc khác nhau.

Tạo tệp **`GroupPolicyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;

public class GroupPolicyDemo {
    public static void main(String[] args) {
        List<String> input = List.of("Lan", "Minh", "Lan");

        Collection<String> registrations = new ArrayList<>();
        Collection<String> uniquePeople = new LinkedHashSet<>();

        registrations.addAll(input);
        uniquePeople.addAll(input);

        printGroup("Lượt đăng ký", registrations);
        printGroup("Người tham gia", uniquePeople);
    }

    private static void printGroup(String label, Collection<String> values) {
        System.out.println(label + " (" + values.size() + "): " + values);
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 GroupPolicyDemo.java
java -Dfile.encoding=UTF-8 GroupPolicyDemo
```

Kết quả stdout:

```text
Lượt đăng ký (3): [Lan, Minh, Lan]
Người tham gia (2): [Lan, Minh]
```

### Vì sao kết quả khác nhau?

- `ArrayList` giữ cả ba lượt đăng ký, bao gồm hai lần `"Lan"`.
- `LinkedHashSet` giữ mỗi giá trị chuỗi một lần và duy trì thứ tự chèn, nên kết quả là `[Lan, Minh]`.
- `printGroup` chỉ cần `size()` và biểu diễn của nhóm để hiển thị, nên tham số `Collection<String>` đáp ứng nhu cầu.

Bài dùng `LinkedHashSet` để thứ tự đầu ra được xác định theo thứ tự chèn. Không nên đổi sang một kiểu set khác rồi mặc định rằng thứ tự in vẫn như cũ.

`List.of(...)` ở đây tạo danh sách đầu vào không thể sửa đổi. Chương trình chỉ đọc nó và dùng `addAll` để đưa các phần tử sang hai collection có khả năng sửa đổi khác. `addAll` thêm các phần tử; nó không biến hai nhóm đích thành góc nhìn tự cập nhật của danh sách đầu vào.

Tình huống này cho thấy: **hợp đồng chung giúp dùng lại mã thao tác, còn loại tập hợp quyết định các quy tắc của dữ liệu**.

## 7. Collection quản lý tham chiếu đến đối tượng

Với `Collection<String>`, các phần tử là tham chiếu tới đối tượng `String`. Với `Collection<Customer>`, các phần tử là tham chiếu tới đối tượng `Customer`.

Cần phân biệt hai loại thay đổi:

- **Thay đổi cấu trúc nhóm:** thêm, xóa hoặc thay thế phần tử theo khả năng của kiểu tập hợp.
- **Thay đổi đối tượng bên trong:** cập nhật dữ liệu của một đối tượng khả biến đang được tham chiếu.

Một collection không cho phép sửa đổi cấu trúc không tự làm cho các đối tượng khả biến bên trong trở nên bất biến. Thêm một đối tượng vào collection cũng không mặc nhiên tạo bản sao độc lập của đối tượng đó.

Nếu hai biến cùng tham chiếu tới một collection, thay đổi qua một biến có thể được quan sát qua biến còn lại. Vì vậy, khi truyền collection giữa các phần của chương trình, cần thống nhất bên nào có quyền sửa và bên nhận có cần một bản sao hay không.

Xóa một phần tử khỏi collection chỉ loại bỏ phần tử đó khỏi nhóm. Đối tượng có thể vẫn được tham chiếu từ nơi khác; lệnh xóa không phải lời yêu cầu hủy ngay đối tượng.

### Kiểu nguyên thủy và lớp bao

Không thể khai báo `Collection<int>`. Kiểu tham số của generics phải là kiểu tham chiếu, nên thường dùng `Collection<Integer>` để quản lý các số nguyên theo mô hình collection.

Java có thể tự đóng hộp giá trị `int` thành `Integer` trong những ngữ cảnh phù hợp. Khi lựa chọn giữa mảng số nguyên và collection số nguyên, cần tính đến sự khác biệt này thay vì coi hai mô hình lưu trữ là giống hệt nhau.

## 8. Những điều hợp đồng Collection chưa quyết định

Biết một đối tượng có kiểu `Collection<E>` vẫn chưa trả lời được mọi câu hỏi:

| Câu hỏi | Điều cần kiểm tra |
| --- | --- |
| Có cho phép phần tử trùng? | Quy tắc của kiểu tập hợp |
| Duyệt theo thứ tự nào? | Cam kết thứ tự của lớp triển khai |
| Có cho phép `null`? | Hợp đồng cụ thể của collection |
| Có thể thêm hoặc xóa? | Khả năng sửa đổi và thao tác tùy chọn |
| Có lấy bằng chỉ số được không? | Giao diện sử dụng có cung cấp thao tác đó không |
| Có an toàn khi nhiều luồng cùng dùng? | Cơ chế đồng thời hoặc đồng bộ hóa được quy định |
| Thao tác tìm hoặc xóa có nhanh không? | Cấu trúc lưu trữ, kích thước và mẫu sử dụng |

Ví dụ:

- `List.of(...)` không chấp nhận phần tử `null` và không hỗ trợ các thay đổi cấu trúc như `add`.
- Một collection khả biến thông thường không mặc nhiên an toàn cho nhiều luồng cùng sửa.
- `size()` là số phần tử; nó không phải thông tin về dung lượng bộ nhớ dự phòng bên trong.
- Các thao tác `contains` hoặc `remove` có thể có chi phí khác nhau giữa các lớp triển khai.

Nên xem giao diện là hợp đồng tối thiểu mà đoạn mã dựa vào, rồi kiểm tra các bảo đảm bổ sung của đối tượng thực tế.

## 9. Chọn collection theo bài toán

Có thể bắt đầu bằng một quy trình ngắn:

1. **Xác định một phần tử là gì.** Trong ứng dụng công việc, đó có thể là chuỗi mô tả hoặc một đối tượng `Task` có mã và trạng thái.
2. **Xác định quy tắc của nhóm.** Có được trùng, có cần thứ tự, có cần chọn phần tử ở đầu hay cần tra theo khóa?
3. **Xác định những thao tác chính.** Chủ yếu duyệt, tìm, lấy theo chỉ số, thêm cuối hay lấy phần tử để xử lý?
4. **Chọn giao diện phù hợp.** Dựa vào nhu cầu sử dụng thay vì chọn ngay tên một lớp quen thuộc.
5. **Chọn lớp triển khai.** Kiểm tra khả năng sửa đổi, thứ tự, giá trị hợp lệ, chi phí và yêu cầu đồng thời.
6. **Kiểm chứng bằng ví dụ nhỏ.** Dùng dữ liệu có phần tử trùng, nhóm rỗng và thao tác không tìm thấy.

Một số cách đặt bài toán:

| Bài toán | Hướng mô hình hóa ban đầu |
| --- | --- |
| Danh sách các công việc theo vị trí người dùng sắp xếp | `List` |
| Tập mã công việc đã hoàn thành, mỗi mã chỉ xuất hiện một lần | `Set` |
| Các công việc đang chờ được lấy ra xử lý | `Queue`, với chính sách lấy phần tử được xác định |
| Tìm thông tin công việc bằng mã | `Map` |

Đây là điểm xuất phát. Ví dụ, “danh sách công việc” trong ngôn ngữ tự nhiên chưa đủ để kết luận phải dùng `List`; nếu yêu cầu chính là tìm theo mã, cấu trúc khóa–giá trị có thể cần thiết hơn.

## 10. Lỗi thường gặp

### Nhầm Collection với ArrayList

`Collection` là giao diện rộng hơn một lớp triển khai. Những điều đúng với `ArrayList` như truy cập theo chỉ số hoặc thứ tự danh sách không thể áp dụng nguyên trạng cho mọi collection.

### Mặc định collection nào cũng thay đổi được

Lệnh `add` có mặt trong giao diện nhưng đối tượng cụ thể có thể không hỗ trợ thao tác đó và ném `UnsupportedOperationException`. Cần kiểm tra nguồn tạo collection và hợp đồng của nó.

### Dùng size như độ dài mảng hoặc dung lượng dự phòng

Mảng dùng thuộc tính `length`; collection dùng phương thức `size()`. Hai mô hình không có cùng cơ chế quản lý chỗ trống.

### Mặc định dữ liệu trùng sẽ tự bị loại

Ví dụ `ArrayList` giữ hai lần `"Viết mã"`. Nếu muốn duy nhất, hãy chọn mô hình và quy tắc so sánh phù hợp thay vì kỳ vọng thao tác `add` tự làm sạch dữ liệu.

### Vừa duyệt vừa tự ý thay đổi cấu trúc

Không nên thêm hoặc xóa trực tiếp theo một cách tùy ý trong lúc duyệt bằng for-each. Hành vi phụ thuộc loại collection và cơ chế duyệt; một số cách dùng có thể gây lỗi khi thay đổi đồng thời cấu trúc.

Ở bước học thao tác duyệt, hãy chọn cơ chế được hỗ trợ, chẳng hạn thao tác của iterator hoặc `removeIf` trên collection cho phép xóa. Việc một lần chạy chưa báo lỗi không chứng minh cách duyệt và sửa là hợp lệ.

### Chọn kiểu chỉ vì quen tên

Hãy viết ra quy tắc dữ liệu trước. Nếu yêu cầu “không được trùng” hoặc “tìm theo mã” chưa được đáp ứng, đổi một vòng lặp đẹp hơn cũng chưa giải quyết đúng bài toán.

## 11. Thực hành

### Bài tập 1: dự đoán trước khi chạy

Với `CollectionIntroDemo`:

1. Đổi chuỗi cần xóa từ `"Viết mã"` thành `"Chưa có"`.
2. Dự đoán giá trị boolean của lần xóa đó.
3. Dự đoán số phần tử và hai lần xuất hiện của `"Viết mã"` còn lại.
4. Chạy lại và đối chiếu với dự đoán.

Điểm cần kiểm chứng: một lần xóa không tìm thấy phải không làm giảm số phần tử; khả năng chứa phần tử trùng vẫn do loại tập hợp quyết định.

### Bài tập 2: làm rõ quy tắc duy nhất

Trong `GroupPolicyDemo`, đổi đầu vào thành `Lan, Minh, Lan, An, Minh`.

Trước khi chạy, hãy viết ra:

- Số lượt đăng ký.
- Số giá trị tên duy nhất.
- Thứ tự xuất hiện trong nhóm `LinkedHashSet`.

Với quy tắc đang dùng, hai nhóm cần có kích thước lần lượt là `5` và `3`; nhóm duy nhất có thứ tự `Lan, Minh, An`.

### Bài tập 3: chọn mô hình trước khi viết mã

Bạn cần quản lý các đơn hàng. Hãy chọn mô hình cho từng yêu cầu độc lập và giải thích:

- Giữ các lần khách thêm hàng theo thứ tự.
- Ghi nhận tập mã đơn đã gửi thông báo, không gửi trùng theo mã.
- Tra thông tin đơn hàng bằng mã đơn.
- Nhận các đơn đang chờ xử lý theo một chính sách rõ ràng.

Với mỗi trường hợp, nêu loại phần tử, yêu cầu về trùng lặp, thứ tự và thao tác chính. Sau đó mới chọn giao diện cùng lớp triển khai để làm ví dụ.
