# Trạng thái thay đổi trong Comparator làm kết quả sắp xếp không ổn định

## 1. Vấn đề cần hiểu

`Comparator<T>` biểu diễn quy tắc xác định thứ tự giữa hai đối tượng cùng kiểu `T`. Các API như `List.sort`, `Collections.sort`, `Stream.sorted`, `TreeSet`, `TreeMap` và `PriorityQueue` có thể gọi `compare(a, b)` nhiều lần để đưa ra quyết định.

Nếu một comparator **đọc trạng thái có thể thay đổi** (cờ đảo chiều, thời gian hiện tại, cấu hình toàn cục, số lần so sánh, dữ liệu từ dịch vụ bên ngoài hoặc thuộc tính mutable của phần tử), quan hệ thứ tự mà nó trả về có thể đổi giữa các lần gọi.

Ví dụ cùng hai đối tượng `a` và `b`:

```text
Lần 1: compare(a, b) = -1  -> a đứng trước b
Lần 2: compare(a, b) = +1  -> a đứng sau b
```

Nếu dữ liệu của hai đối tượng và tiêu chí so sánh về mặt nghiệp vụ lẽ ra không đổi, hai kết quả trái chiều cho thấy thuật toán đang nhận các quyết định mâu thuẫn. Sắp xếp có thể cho thứ tự không như mong đợi, hoặc một triển khai có thể phát hiện việc vi phạm hợp đồng và ném ngoại lệ. Không được mặc định thuật toán sẽ luôn phát hiện lỗi.

Điểm mấu chốt: **đối với một thao tác sắp xếp, bộ tiêu chí so sánh cần tạo ra một quan hệ thứ tự nhất quán từ đầu tới cuối**. Với collection có thứ tự luôn được duy trì như `TreeSet`/`TreeMap`, tiêu chí phải tiếp tục nhất quán trong thời gian các phần tử/khóa còn nằm trong cấu trúc.

## 2. Hợp đồng `Comparator.compare()` yêu cầu gì?

Với `Comparator<T> comparator`, `compare(x, y)` trả số nguyên âm, `0` hoặc dương để diễn tả `x` đứng trước, tương đương theo comparator, hoặc đứng sau `y`. **Giá trị số cụ thể** như `-1` hoặc `1` không có nghĩa đặc biệt; điều cần xét là dấu.

Javadoc `Comparator` quy định các tính chất logic của quan hệ thứ tự:

1. **Đổi hai đối số phải đảo dấu:** `signum(compare(x, y)) == -signum(compare(y, x))`. Một comparator không được đồng thời khẳng định `x < y` và `y < x`.
2. **Tính bắc cầu:** nếu `compare(x, y) > 0` và `compare(y, z) > 0` thì `compare(x, z) > 0`.
3. **Tính tương đương nhất quán:** nếu `compare(x, y) == 0` thì với mọi `z` hợp lệ, `compare(x, z)` và `compare(y, z)` phải cùng dấu.

Những tính chất trên mô tả **một quan hệ thứ tự nhất quán**. Nếu comparator thay đổi cách đánh giá trong khi thuật toán đang dựa vào nó, quan hệ tổng thể có thể không còn thỏa những giả định đó.

Lưu ý quan trọng: tài liệu nói `Comparator` có thứ tự **consistent with equals** khi `compare(a, b) == 0` tương đương với `a.equals(b)`. Đây là đặc tính rất nên có khi dùng `TreeSet`/`TreeMap` để đáp ứng hợp đồng `Set`/`Map`, nhưng một comparator không nhất quán với `equals` **không tự động** có nghĩa là nó thay đổi theo thời gian. Đó là **hai vấn đề riêng**.

## 3. Ba nguồn trạng thái khiến comparator đổi kết quả

### 3.1. Biến điều khiển bên ngoài

Ví dụ comparator dùng cờ `descending`:

```java
Comparator<Integer> comparator =
        (a, b) -> descending
                ? Integer.compare(b, a)
                : Integer.compare(a, b);
```

Đoạn trên là **mảnh mã minh họa** giả sử đã có biến trạng thái `descending`. Khi cờ đổi từ `false` sang `true`, cùng cặp `1` và `2` chuyển từ “1 trước 2” sang “1 sau 2”.

**Đảo chiều giữa hai lần sắp xếp độc lập có thể là yêu cầu nghiệp vụ hoàn toàn hợp lệ.** Rủi ro xuất hiện khi comparator đọc cờ **trong cùng một lần sắp xếp đang diễn ra**, hoặc khi một collection đã lập cấu trúc theo thứ tự cũ nhưng vẫn dùng chính comparator nay đã đổi hướng.

### 3.2. Biến đếm, random và đồng hồ

Những giá trị như `System.currentTimeMillis()`, `Instant.now()`, `Random.nextBoolean()` hoặc biến đếm tăng mỗi lần gọi đều có thể thay đổi trong khi hai đối tượng không đổi.

Ví dụ lỗi khái niệm:

```java
int[] calls = {0};
Comparator<Integer> bad = (a, b) -> {
    calls[0]++;
    return (calls[0] % 2 == 0 ? -1 : 1)
            * Integer.compare(a, b);
};
```

Ở đây, cùng lời gọi `bad.compare(1, 2)` có thể trả `-1` rồi `+1` chỉ vì số lần gọi khác nhau. Đây là **phương thức không đáng dùng để sắp xếp**. Việc mã trên có thể biên dịch không làm nó thỏa hợp đồng thứ tự.

Không nên biến “ai được so sánh trước”, “đã so bao nhiêu lần”, “đang là phút chẵn hay lẻ” thành tiêu chí thứ tự của những giá trị vốn phải xếp ổn định.

### 3.3. Thuộc tính mutable của chính phần tử

Không cần comparator có biến riêng thì kết quả vẫn có thể thay đổi. Ví dụ:

```java
Comparator<Employee> bySalary =
        Comparator.comparingInt(Employee::getSalary);
```

Đây là **đoạn mã minh họa**, giả sử có lớp `Employee` và phương thức `getSalary()`.

Nếu một thread hoặc tác vụ khác sửa lương của nhân viên trong lúc danh sách đang được sắp xếp, những lần gọi comparator có thể đọc trạng thái trước và sau cập nhật. Ngay cả khi comparator tự nó không ghi gì, dữ liệu đầu vào mutable cũng khiến thứ tự thiếu ổn định.

Với `TreeSet<Employee>` hoặc `TreeMap<Employee, ...>` sắp theo lương, việc sửa lương của phần tử/khóa đang lưu cũng làm cấu trúc đã sắp xếp không còn khớp tiêu chí mới. Bảng/cây không tự tái sắp xếp mỗi khi một field trong đối tượng bị sửa.

## 4. Ví dụ đầy đủ chạy được bằng Java 17

Ví dụ tách rõ hai tình huống:

- **An toàn:** chọn comparator tăng dần hoặc giảm dần cố định cho từng thao tác sắp xếp riêng biệt.
- **Không an toàn nếu dùng trong cùng thao tác:** comparator đọc cờ đang thay đổi, hoặc đảo kết quả theo số lần gọi. Chương trình chỉ gọi trực tiếp `compare` để chứng minh lỗi; **không gọi `sort` với comparator sai** vì kết quả và ngoại lệ có thể phụ thuộc thuật toán, kích thước dữ liệu và thứ tự gọi.

Tạo tệp **`ComparatorStateDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.stream.Collectors;

public class ComparatorStateDemo {
    record Task(String name, int priority) {}

    static String names(List<Task> tasks) {
        return tasks.stream().map(Task::name)
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) {
        Comparator<Task> stable = Comparator
                .comparingInt(Task::priority)
                .thenComparing(Task::name);

        Task a = new Task("api", 3);
        Task b = new Task("db", 1);
        Task c = new Task("web", 2);

        List<Task> tasks = List.of(a, b, c);
        List<Task> ascending = new ArrayList<>(tasks);
        ascending.sort(stable);
        System.out.println("ascending: " + names(ascending));

        List<Task> descending = new ArrayList<>(tasks);
        descending.sort(stable.reversed());
        System.out.println("descending: " + names(descending));

        AtomicBoolean reverseFlag = new AtomicBoolean(false);
        Comparator<Task> mutable = (left, right) -> reverseFlag.get()
                ? stable.compare(right, left)
                : stable.compare(left, right);

        System.out.println("pair before: " + mutable.compare(b, c));
        reverseFlag.set(true);
        System.out.println("pair after: " + mutable.compare(b, c));

        int[] calls = {0};
        Comparator<Integer> changingEachCall = (left, right) -> {
            calls[0]++;
            int sign = (calls[0] % 2 == 0) ? -1 : 1;
            return sign * Integer.compare(left, right);
        };
        System.out.println("unstable first: "
                + changingEachCall.compare(1, 2));
        System.out.println("unstable second: "
                + changingEachCall.compare(1, 2));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ComparatorStateDemo.java
java ComparatorStateDemo
```

**Stdout đã kiểm chứng bằng biên dịch và chạy Java:**

```text
ascending: db, web, api
descending: api, web, db
pair before: -1
pair after: 1
unstable first: -1
unstable second: 1
```

Giải thích:

1. `stable` so sánh `priority` rồi dùng `name` làm tiêu chí phụ khi bằng ưu tiên. Vì hai trường của record `Task` ở đây là `int` và `String`, và các instance này không bị sửa, thứ tự so sánh cố định.
2. `stable.reversed()` tạo comparator đảo ngược thứ tự *một cách cố định*. Hai lần sort độc lập có thể tạo ra kết quả tăng dần và giảm dần đúng yêu cầu.
3. `mutable.compare(b, c)` ban đầu trả `-1`, nhưng sau khi đổi `reverseFlag` lại trả `1`. Kết quả của cùng một phép so sánh đã phụ thuộc trạng thái bên ngoài.
4. `changingEachCall` trả `-1` rồi `1` cho đúng một cặp số, dù hai số không hề đổi. Nếu thuật toán sort dựa vào comparator này, các quyết định phân loại sẽ tự mâu thuẫn.
5. `AtomicBoolean` bảo đảm việc đọc/ghi flag có ngữ nghĩa bộ nhớ phù hợp giữa các thread; nó **không** làm một comparator có tiêu chí đổi chiều trở nên ổn định. **Thread-safe trong việc đọc biến không đồng nghĩa với nhất quán của quan hệ thứ tự.**

Phần an toàn của ví dụ dùng comparator khác nhau cho từng lần sort. Phần cố ý sai chỉ minh họa việc lặp lại so sánh; không coi output từ một lần sort sử dụng comparator thay đổi là quy tắc Java phải bảo đảm.

## 5. Điều gì có thể xảy ra trong các API sắp xếp?

### 5.1. `List.sort` và `Collections.sort`

Hai API sắp xếp dựa trên kết quả của nhiều phép so sánh. Khi comparator đổi tiêu chí giữa chừng, thuật toán có thể nhận thông tin “a trước b” ở một lần, “a sau b” ở lần khác.

Hậu quả có thể gồm:

- Danh sách sau khi sắp xếp **không còn tuân theo comparator ở thời điểm kết thúc**.
- Thứ tự phụ thuộc vào số lượng và trình tự so sánh mà thuật toán tình cờ thực hiện.
- Một số triển khai có thể ném `IllegalArgumentException` với thông báo dạng “Comparison method violates its general contract!”. Đây là hành vi **có thể xảy ra**, không phải ngoại lệ được bảo đảm cho mọi comparator sai.
- Nếu phần tử bị một thread khác thay đổi đồng thời, còn có các vấn đề an toàn truy cập collection và dữ liệu. Không được chỉ sửa comparator rồi mặc định mọi cuộc đua đã được loại bỏ.

Đừng viết kiểm thử kiểu “comparator sai phải luôn ném ngoại lệ”. Một mảng nhỏ có thể sắp xếp xong mà không phát hiện lỗi; điều đó **không chứng minh** comparator đúng hợp đồng.

### 5.2. `Stream.sorted(comparator)`

`Stream.sorted` cũng cần một quan hệ so sánh nhất quán khi thực thi terminal operation. Đặt comparator phụ thuộc vào đồng hồ, random hoặc cấu hình có thể bị sửa trong pipeline là sai về mặt thiết kế, ngay cả khi cú pháp stream trông bất biến.

Với stream song song, comparator có trạng thái mutable không đồng bộ còn có thể gây *data race*; kể cả trạng thái được đồng bộ, các thread đọc **những giá trị hợp lệ nhưng khác nhau** vẫn khiến thứ tự thiếu nhất quán. Đồng bộ chỉ là một phần của giải pháp.

### 5.3. `TreeSet` và `TreeMap`

Các collection này dùng **thứ tự do comparator cung cấp** (hoặc natural ordering) để tổ chức và tra cứu phần tử/khóa. Điểm khác biệt quan trọng với một lần sort: chúng cần tiêu chí thứ tự ổn định **trong suốt thời gian các mục đang được lưu**.

Ví dụ, một `TreeSet` được tạo với comparator tăng dần rồi thêm các phần tử. Nếu sau đó cờ bên ngoài làm chính comparator chuyển sang giảm dần, cấu trúc tìm kiếm đã được xây dựng theo quan hệ trước đó. Những thao tác `contains`, `add`, `remove` hoặc duyệt có thể cho kết quả bất ngờ; collection không tự xây dựng lại toàn bộ cây khi cờ đổi.

Ngoài ra, với `TreeSet`/`TreeMap`, **`compare(a,b) == 0`** quyết định hai phần tử/khóa tương đương theo thứ tự. Nếu comparator sử dụng field mutable, hai khóa từng khác nhau có thể trở nên “bằng nhau” theo tiêu chí mới, hoặc ngược lại. Điều đó ảnh hưởng tính duy nhất và tìm kiếm trong collection.

Ví dụ **mảnh mã minh họa** (không phải chương trình độc lập):

```java
TreeSet<Employee> employees =
        new TreeSet<>(Comparator.comparingInt(Employee::getSalary));

Employee employee = new Employee("An", 100);
employees.add(employee);

// Nếu setter thay đổi chính tiêu chí mà cây dùng để định vị:
employee.setSalary(1000);

// Cây không tự tái cấu trúc chỉ vì một thuộc tính của
// đối tượng đã lưu bị sửa; thao tác tra cứu có thể sai kỳ vọng.
```

Cần các import và khai báo lớp `Employee` nếu muốn chạy độc lập. Cách an toàn là tránh sửa thuộc tính khóa/sắp xếp trong khi phần tử nằm trong cây; nếu bắt buộc, **remove trước khi thay đổi**, sau đó sửa và **add lại**, hoặc tạo cấu trúc mới từ snapshot dữ liệu đã cố định. Không dựa vào việc `remove` bằng đối tượng đã sửa còn tìm thấy entry cũ.

### 5.4. `PriorityQueue`

`PriorityQueue` dùng comparator để quyết định phần tử có độ ưu tiên cao nhất theo quy ước của hàng đợi. Nếu comparator thay đổi tiêu chí sau khi các phần tử đã được thêm, cấu trúc heap hiện có không tự sửa vị trí mọi phần tử theo thứ tự mới. Một phép `peek` hoặc `poll` sau đó có thể không phản ánh ưu tiên vừa thay đổi.

Khi cần đổi toàn bộ chính sách ưu tiên, tạo một priority queue mới sử dụng comparator cố định mới và đưa các phần tử từ snapshot hiện tại vào, thay vì đổi trạng thái bên trong comparator cũ rồi tiếp tục dùng hàng đợi.

## 6. Ba loại “ổn định” dễ bị nhầm lẫn

### 6.1. Comparator nhất quán

Cùng dữ liệu, cùng tiêu chí, các lần so sánh phải biểu diễn cùng quan hệ thứ tự. Đây là trọng tâm của bài. Để comparator ổn định, đầu vào dùng cho phép so sánh và cấu hình của nó phải giữ giá trị phù hợp trong khoảng sử dụng.

### 6.2. Thuật toán sắp xếp ổn định (stable sort)

Một thuật toán sort được gọi là **stable** nếu hai phần tử được comparator xem là bằng nhau (`compare(a,b) == 0`) vẫn giữ **thứ tự tương đối ban đầu** trong kết quả. Theo tài liệu Java, `List.sort` là phép sắp xếp ổn định.

Điều đó **không cứu** một comparator thay đổi. Stable sort chỉ có ý nghĩa khi comparator đã cho một quan hệ thứ tự hợp lệ. Nếu `compare` thay kết quả giữa chừng, câu hỏi “hai phần tử bằng nhau theo comparator” không còn một câu trả lời nhất quán.

### 6.3. Kết quả ổn định qua nhiều lần chạy

Ngay cả comparator hoàn toàn đúng, nhiều phần tử có cùng khóa so sánh có thể tạo ra những kết quả khác khi **thứ tự đầu vào khác**. Một stable sort bảo toàn thứ tự của những phần tử được xem là tương đương, nên sự khác biệt ở thứ tự đầu vào vẫn có thể được giữ lại.

Nếu cần thứ tự kết quả hoàn toàn xác định, bổ sung **tie-breaker** phù hợp, chẳng hạn sắp theo `priority` rồi theo `id`:

```java
Comparator<Task> byPriorityAndId = Comparator
        .comparingInt(Task::priority)
        .thenComparing(Task::id);
```

Đây là **mảnh mã minh họa** giả sử `Task` có accessor `priority()` và `id()`. Comparator này chỉ tạo thứ tự xác định khi giá trị các accessor ổn định và tiêu chí phụ đủ để phân biệt những phần tử cần phân biệt. Nếu hai đối tượng khác nhau vẫn có cùng cả hai tiêu chí, chúng tiếp tục được comparator coi là bằng nhau.

## 7. Thiết kế comparator không phụ thuộc trạng thái thay đổi

### 7.1. Cố định cấu hình tại thời điểm tạo comparator

Thay vì đọc biến cấu hình đang có thể thay đổi ở **mỗi** lần `compare`, hãy chụp giá trị cấu hình trước khi bắt đầu:

```java
boolean descendingSnapshot = currentDescendingSetting;
Comparator<Item> base =
        Comparator.comparingInt(Item::getRank);

Comparator<Item> chosen = descendingSnapshot
        ? base.reversed()
        : base;
```

Đây là **đoạn mã minh họa**, giả sử `currentDescendingSetting`, `Item` và `getRank()` được định nghĩa phù hợp. Biến `descendingSnapshot` cố định hướng sắp xếp cho comparator được chọn. Nếu cần đổi chính sách, tạo comparator mới và sort lại.

Không nên đổi biến global giữa các lần so sánh rồi trông cậy thuật toán sẽ chỉ đọc nó một lần.

### 7.2. Chụp dữ liệu thuộc tính trước khi sắp xếp

Khi tiêu chí phụ thuộc dữ liệu có thể đổi (giá thị trường, điểm động, số lượt xem, trạng thái nghiệp vụ), có thể tạo **snapshot bất biến**:

```java
record RankedItem(String id, int scoreSnapshot) {}

Comparator<RankedItem> byScore =
        Comparator.comparingInt(RankedItem::scoreSnapshot)
                  .thenComparing(RankedItem::id);
```

Đây là **đoạn mã minh họa**. Quy trình phù hợp là đọc điểm số tại một thời điểm xác định, xây dựng các `RankedItem`, rồi sắp xếp snapshot. Khi nguồn dữ liệu thay đổi, tạo snapshot mới thay vì âm thầm đổi quan hệ so sánh của những phần tử đang nằm trong cấu trúc.

Record chỉ làm các trường thành `final`; nếu một record chứa tham chiếu đến một đối tượng mutable, **nội dung bên trong tham chiếu đó vẫn có thể thay đổi**. Chọn component bất biến hoặc sao chép phòng vệ khi cần.

### 7.3. Tách so sánh khỏi side effect

`compare` nên chỉ **đọc dữ liệu liên quan** và trả kết quả. Tránh:

- Tăng biến đếm **ảnh hưởng tiêu chí xếp hạng** mỗi lần so sánh.
- Gọi setter, cập nhật database hoặc ghi vào object ngay trong comparator.
- Gọi API bên ngoài để lấy giá trị mới cho cùng đối tượng ở các lần so sánh.
- Sinh số ngẫu nhiên để giải quyết trường hợp hòa.
- Đọc thời gian hiện tại để đảo thứ tự liên tục.

Nếu nghiệp vụ cần tie-break ngẫu nhiên, **sinh seed hoặc thứ tự phụ trước khi sort** và giữ giá trị đó cố định trong suốt phép sắp xếp. Nếu nghiệp vụ cần so thời điểm, hãy so các timestamp đã được lưu/chụp, thay vì hỏi “bây giờ là mấy giờ?” bên trong comparator mỗi lần.

### 7.4. Tránh tràn số và sai logic

Ngay cả comparator không có mutable state cũng có thể sai. Ví dụ:

```java
Comparator<Integer> wrong = (a, b) -> a - b;
```

Phép trừ có thể tràn `int` và gây đảo dấu không hợp lý với các giá trị biên. Dùng:

```java
Comparator<Integer> right = Integer::compare;
```

Khi sắp theo thuộc tính, ưu tiên `Comparator.comparingInt`, `comparingLong`, `comparing`, `thenComparing`; chúng giúp biểu đạt rõ tiêu chí và tránh nhiều lỗi so sánh thủ công.

Đây là vấn đề độc lập nhưng liên quan: một comparator “cố định trạng thái” mà vi phạm tính bắc cầu hay đổi dấu cũng không được xem là hợp lệ.

## 8. Comparator, đồng thời và quyền sửa dữ liệu

Trong hệ thống đa luồng, việc dùng `AtomicBoolean` hoặc `volatile` để đọc cờ có thể giúp thread này **thấy được** cập nhật từ thread khác. Nhưng nếu giá trị được nhìn thấy thay đổi giữa hai lời gọi, quan hệ thứ tự vẫn bị đảo. Cách giải quyết tốt hơn:

1. Chốt cấu hình trước khi bắt đầu thao tác sort.
2. Tạo snapshot nhất quán của các thuộc tính cần so sánh.
3. Không cho thread khác sửa dữ liệu/snapshot đang dùng trong sort.
4. Nếu cần công bố kết quả sau khi tính xong, công bố danh sách hoặc collection mới bằng chiến lược đồng bộ an toàn thích hợp.
5. Với collection luôn được tổ chức theo thứ tự như `TreeMap`, `TreeSet`, `PriorityQueue`, xây lại cấu trúc khi quan hệ xếp hạng thực sự thay đổi.

Đừng coi `Collections.synchronizedList`, `volatile` trên một field hoặc thread-safe flag là giải pháp tự động cho **một phép so sánh phụ thuộc nhiều dữ liệu**. Bất biến hoặc snapshot nhất quán mới giải quyết tính ổn định của tiêu chí.

## 9. Kiểm tra và review comparator

Có thể đánh giá một comparator bằng các câu hỏi sau:

- Khi gọi `compare(a,b)` nhiều lần với dữ liệu không đổi, kết quả **cùng dấu** không?
- `compare(a,b)` và `compare(b,a)` có dấu đối nhau không?
- Các quan hệ `a > b`, `b > c` có kéo theo `a > c` không?
- Khi `compare(a,b)==0`, dấu so sánh của `a` và `b` với một `c` có giống nhau không?
- Comparator có đọc `now()`, random, môi trường, config mutable, cơ sở dữ liệu, hoặc field mutable của phần tử không?
- Những giá trị đó có được **cố định trong khoảng sử dụng** không?
- Nếu dùng `TreeSet/TreeMap`, thứ tự có nhất quán với `equals` khi ứng dụng cần tuân thủ đầy đủ hợp đồng `Set/Map` không?
- Sau khi phần tử được đưa vào cấu trúc có thứ tự, có code nào sửa tiêu chí định vị của nó không?

Một phép thử lặp ngắn (đặt **bên trong phương thức** của một lớp kiểm thử có comparator và dữ liệu hợp lệ):

```java
int first = Integer.signum(comparator.compare(a, b));
int second = Integer.signum(comparator.compare(a, b));
if (first != second) {
    throw new AssertionError("Comparator khong on dinh");
}
```

Đây là **mảnh kiểm thử minh họa**, không phải một chương trình độc lập. Nó bắt được một số lỗi biến trạng thái, nhưng không chứng minh mọi đầu vào hoặc mọi lịch thực thi đa luồng. Cần kết hợp với kiểm thử các bộ ba phần tử, dữ liệu biên, và review đường đọc dữ liệu của comparator.

Nếu một lần chạy sort có kết quả bất thường hoặc ném `IllegalArgumentException` liên quan hợp đồng so sánh, hãy ưu tiên kiểm tra **logic, dữ liệu và trạng thái comparator** trước khi điều tra thuật toán sort. Tuy vậy, ngoại lệ đó không phải phương pháp chẩn đoán duy nhất và không xuất hiện ở mọi trường hợp.

## 10. Tình huống thực tế

**Bảng xếp hạng:** điểm số cập nhật liên tục trong database. Không gọi API lấy điểm mới ngay trong `compare`; thay bằng chụp điểm tại thời điểm công bố, rồi sắp xếp các snapshot.

**UI có nút đảo chiều:** mỗi lần nhấn nút tạo danh sách sắp xếp mới với `comparator.reversed()`. Đây là hành vi hợp lệ; đảm bảo nút nhấn giữa một thao tác sort không làm comparator đang chạy đổi hướng.

**Hàng đợi ưu tiên công việc:** khi chính sách ưu tiên thay đổi, tạo `PriorityQueue` mới với comparator mới và nạp lại các công việc cần giữ. Đừng đổi biến ưu tiên mà heap cũ đang tham chiếu.

**Tập nhân viên có thứ tự theo lương:** nếu lương thay đổi, đừng sửa trực tiếp trường xếp hạng khi đối tượng vẫn nằm trong `TreeSet`, rồi chờ cây tự di chuyển phần tử. Thiết kế theo khóa bất biến hoặc quản lý thao tác gỡ/thêm bằng giá trị cũ và mới.

**Sắp xếp theo tên ngôn ngữ:** có thể dùng `Collator` để so chuỗi theo locale, nhưng không thay đổi cấu hình hay dùng chung một đối tượng cấu hình có thể sửa trong lúc sort. Khởi tạo bộ so sánh có cấu hình cố định cho thao tác cần làm.

## 11. Tổng kết kiến thức cần nhớ

- Comparator phải cung cấp **quan hệ thứ tự nhất quán** cho dữ liệu mà thuật toán đang xử lý; cùng cặp không nên đổi dấu chỉ vì một biến ngoài đổi hoặc số lần gọi tăng.
- Tránh đọc thời gian hiện tại, random, config mutable, số đếm hay thuộc tính đang bị sửa trong `compare`.
- **Thay comparator giữa hai lần sort độc lập là hợp lệ** nếu mỗi lần sort sử dụng một tiêu chí nhất quán; **đổi tiêu chí trong lúc sort** mới gây rủi ro trực tiếp.
- `TreeSet`, `TreeMap` và `PriorityQueue` lưu cấu trúc tổ chức theo comparator; khi quan hệ thứ tự đổi, thường phải xây lại cấu trúc.
- Stable sorting algorithm, thread-safe flag và “comparator nhất quán” là các khái niệm khác nhau; một cái không tự bảo đảm cái còn lại.
- Dùng comparator cố định, snapshot dữ liệu, tie-breaker rõ ràng và các helper như `Comparator.comparingInt`/`thenComparing` để có kết quả dễ kiểm chứng.
- Java có thể phát hiện vi phạm ở một số tình huống và ném ngoại lệ, nhưng **không bảo đảm luôn phát hiện**; trách nhiệm bảo toàn hợp đồng thuộc về cách thiết kế comparator.
