# Giới hạn phạm vi biến để dễ hiểu kiểu suy luận (`var` trong Java 10+)

## 1. Mục tiêu học tập

Trong Java, `var` cho phép trình biên dịch suy luận **kiểu tĩnh** của một biến cục bộ từ biểu thức khởi tạo. Khi đọc code, người lập trình thường phải nhìn lại biểu thức đó để hiểu chính xác biến có kiểu gì. Nếu biến được khai báo ở đầu một phương thức rất dài rồi mới được sử dụng hàng chục dòng phía dưới, việc đọc, sửa và review dễ trở nên khó khăn.

Một thực hành quan trọng là **giới hạn phạm vi của biến và đặt khai báo càng gần nơi sử dụng đầu tiên càng hợp lý**. Điều này giúp:

- Nhìn được tên, initializer, kiểu suy luận và hành động trên biến trong một đoạn code ngắn.
- Giảm số nhánh, phép gán và thao tác phải theo dõi khi suy luận ý nghĩa của biến.
- Phát hiện nhanh hậu quả khi initializer thay đổi và khiến kiểu suy luận khác đi.
- Giảm nguy cơ vô tình dùng nhầm biến ở phần code không liên quan.
- Tạo những khối lệnh và phương thức tập trung vào một trách nhiệm.

**Mục tiêu sau bài:** bạn có thể phân biệt phạm vi cú pháp với khoảng cách sử dụng thực tế; xác định phạm vi của `var` trong khối, `for`, enhanced `for` và `try-with-resources`; refactor đoạn mã dài; chọn tên biến và kiểu khai báo thích hợp; nhận diện các lỗi phổ biến và kiểm tra kết quả bằng Java 17+.

Quy tắc `var` từ Java 10 và các hướng dẫn thu hẹp phạm vi biến đều **tiếp tục có giá trị trong Java hiện đại**. Bài sử dụng kiến thức còn áp dụng và không dựa trên hành vi đã lỗi thời.

## 2. Mối liên hệ giữa `var`, kiểu suy luận và phạm vi

Xem ví dụ:

```java
var count = names.size(); // count được suy luận là int
System.out.println(count);
```

Tại thời điểm biên dịch, compiler dựa vào kiểu trả về của `names.size()`, suy luận `count` là `int`. Khi đọc hai dòng liền kề, bạn dễ biết `count` lấy từ đâu và được dùng để làm gì.

Nếu khai báo được đặt xa hàng trăm dòng so với câu lệnh dùng, người đọc phải nhớ hoặc tìm lại `names`, `size()` và lịch sử thao tác trên `count`. Vấn đề chính không phải Java “mất kiểu”; kiểu tĩnh vẫn được compiler kiểm tra, nhưng **con người mất ngữ cảnh quan sát**.

### Ba khái niệm khác nhau

1. **Kiểu tĩnh:** được suy luận một lần từ initializer, không đổi khi biến được gán lại.
2. **Phạm vi cú pháp (lexical scope):** khu vực trong mã nguồn mà tên biến có thể được tham chiếu hợp lệ, được quy định bởi khối, vòng lặp, resource specification và các cấu trúc ngôn ngữ.
3. **Khoảng cách sử dụng thực tế:** số dòng, nhánh và thao tác từ nơi khai báo đến nơi biến được đọc hoặc ghi. Đây là thước đo hỗ trợ khả năng đọc, **không phải một quy tắc của compiler**.

Một biến có thể có phạm vi cú pháp dài nhưng chỉ được sử dụng gần khai báo; khi đó vẫn nên cân nhắc đặt khai báo trong một khối hoặc phương thức nhỏ hơn. Ngược lại, một biến trong phương thức ngắn vẫn có thể gây khó hiểu nếu tên chung chung hoặc initializer che giấu kiểu.

## 3. Vì sao phạm vi dài gây khó khi dùng `var`?

```java
// Đoạn minh họa trong một phương thức; services và dữ liệu đã được cung cấp.
var result = service.fetch();

// ... nhiều bước xử lý không liên quan ...

send(result);
```

Chỉ nhìn `send(result)` không thể biết ngay `result` là `String`, `List<Order>` hay kiểu khác. Người đọc thường phải tìm ngược đến `service.fetch()` và có thể tiếp tục mở định nghĩa của phương thức `fetch`.

Nếu initializer thay đổi:

```java
var result = service.fetchNewVersion();
```

thì kiểu suy luận của `result` có thể đổi. Với biến có phạm vi lớn, các tác động lên overload, gán lại, generic hoặc phương thức được gọi cũng có thể nằm xa nhau và khó kiểm tra hơn.

**Nguyên tắc:** giữ một nhóm biến cục bộ phục vụ cùng một nhiệm vụ gần nhau và giới hạn vùng mã cần theo dõi. Nếu kiểu của biến là hợp đồng quan trọng mà initializer khó đọc, **kiểu tường minh vẫn có thể thích hợp hơn `var`**.

## 4. Phạm vi của biến trong các cấu trúc Java

`var` không tự thay đổi quy tắc phạm vi của Java: một biến được khai báo bằng `var` có phạm vi như biến cục bộ khai báo bằng kiểu tường minh ở cùng vị trí.

| Vị trí khai báo | Kiểu được suy luận từ đâu? | Phạm vi sử dụng của tên biến |
| --- | --- | --- |
| Khối lệnh `{ ... }` | Initializer ở khai báo | Trong phần còn lại của khối tương ứng kể từ khai báo (kể cả khối lồng bên trong nếu không xung đột). |
| `for (var i = 0; ...; ...)` | Biểu thức `0` | Trong initializer, điều kiện, bước cập nhật và phần thân của vòng `for` theo quy tắc ngôn ngữ; không sử dụng sau khi vòng kết thúc. |
| `for (var item : items)` | Kiểu phần tử của mảng hoặc `Iterable` | Trong thân của enhanced `for`. |
| `try (var reader = ... ) { ... }` | Biểu thức tài nguyên có kiểu thích hợp | Từ khai báo trong resource specification qua phần còn lại của danh sách tài nguyên và thân `try`; không dùng trong các `catch`/`finally` của câu lệnh đó. |
| Biến trong nhánh `if` có khối riêng | Initializer tại nhánh đó | Trong khối nhánh tương ứng, từ vị trí khai báo. |
| Biến trong thân một phương thức con | Initializer của phương thức con | Chỉ trong phương thức con; không thể tham chiếu trực tiếp từ phương thức gọi. |

Bảng mô tả các trường hợp thực hành thường gặp. Về mặt cú pháp, JLS `6.3 quy định chính xác scope cho từng loại khai báo.

### 4.1. Biến trong khối lệnh

```java
{
    var title = "Java"; // String
    System.out.println(title);
}
// System.out.println(title); // LỖI: title nằm ngoài phạm vi
```

Cặp dấu `{ ... }` tạo ranh giới rõ ràng cho việc sử dụng `title`. Biến không cần tồn tại trong phần mã sau khối nếu không có nhiệm vụ ở đó.

**Lưu ý:** Java không cho phép tùy ý khai báo lại một biến cục bộ cùng tên trong một khối lồng khi biến ngoài còn trong phạm vi. Đừng thêm khối chỉ để “shadow” biến cũ. Dùng tên khác có nghĩa hoặc đặt các biến trùng tên trong những phạm vi rời nhau thực sự.

### 4.2. Biến khởi tạo của basic `for`

```java
for (var index = 0; index < 3; index++) {
    System.out.println(index);
}
// System.out.println(index); // LỖI: index không còn trong phạm vi
```

`index` có kiểu `int` từ initializer `0` và chỉ gắn với vòng lặp. Nếu chỉ cần bộ đếm cho vòng lặp, đặt nó ở `for` sẽ tốt hơn khai báo trước ở đầu phương thức.

### 4.3. Biến trong enhanced `for`

```java
java.util.List<String> names = java.util.List.of("An", "Binh");
for (var name : names) { // name có kiểu String
    System.out.println(name);
}
// name không thể dùng ở đây
```

Không phải viết `var name = ...` trong enhanced `for`; kiểu phần tử suy luận từ nguồn `names`. Nếu chỉ xử lý từng phần tử, cách khai báo ngay trong vòng lặp thể hiện được phạm vi sử dụng tối thiểu.

### 4.4. Resource trong `try-with-resources`

```java
try (var reader = new java.io.BufferedReader(
        new java.io.StringReader("hello"))) {
    var line = reader.readLine();
    System.out.println(line);
}
// reader và line không còn trong phạm vi ở đây
```

Đây là **đoạn minh họa đặt trong phương thức xử lý hoặc khai báo `throws IOException` phù hợp**. Tài nguyên `reader` có phạm vi gắn với phần quản lý tài nguyên của `try` và được đóng tự động sau khi phần `try` kết thúc. Khi đọc mã, người khác dễ xác định thời điểm tạo và sử dụng tài nguyên.

### 4.5. Phạm vi của biến trong một nhánh

```java
if (ready) {
    var statusMessage = "Ready";
    System.out.println(statusMessage);
}
// statusMessage không thể được tham chiếu ở đây
```

Giả sử `ready` là một `boolean` được định nghĩa trong phương thức. Đừng khai báo `statusMessage` bên ngoài `if` nếu nó chỉ cần dùng bên trong nhánh này.

## 5. Đặt khai báo gần nơi sử dụng đầu tiên

### Trước: khai báo quá sớm

```java
// Đoạn minh họa nằm trong một phương thức.
var normalizedName = inputName.trim();

validateUserPermissions();
updateMetrics();
logRequest();

System.out.println(normalizedName);
```

Giả sử các phương thức liên quan đã được khai báo. Khoảng cách lớn giữa khởi tạo và sử dụng khiến người đọc phải giữ thông tin về `normalizedName` xuyên qua nhiều bước khác.

### Sau: khai báo ngay trước nơi cần

```java
validateUserPermissions();
updateMetrics();
logRequest();

var normalizedName = inputName.trim();
System.out.println(normalizedName);
```

Dời khai báo giúp đoạn đọc `normalizedName` dễ hiểu hơn. Tuy nhiên, **chỉ dời phép tính khi không làm đổi hành vi**: nếu `inputName` có thể bị thay đổi giữa các bước, hoặc phép tính có side effect/ngoại lệ phụ thuộc thứ tự, hai phiên bản có thể không tương đương. Khi refactor, phải xét phụ thuộc dữ liệu và thứ tự thực thi.

**Thực hành:** nếu giá trị chỉ cần ở đoạn cuối, hãy khai báo muộn. Nếu giá trị phải được tính sớm để giữ snapshot hoặc kiểm tra trước những thao tác khác, giữ điểm tính phù hợp và có thể tách nhiệm vụ thành phương thức nhỏ.

## 6. Tạo khối nhỏ khi biến chỉ phục vụ một nhiệm vụ

Có những trường hợp một phương thức phải làm nhiều việc liên tiếp nhưng ta muốn biến trung gian chỉ tồn tại trong một phần:

```java
{
    var displayName = rawName.trim();
    var message = "Hello, " + displayName;
    System.out.println(message);
}

{
    var count = results.size();
    System.out.println("Total: " + count);
}
```

Đây là **hai khối minh họa trong cùng một phương thức**, giả sử `rawName` và `results` đã tồn tại. Mỗi khối có phạm vi tên biến riêng; thông tin phục vụ việc hiển thị lời chào không lan sang việc thống kê.

Không cần bọc mọi hai dòng code trong ngoặc nhọn. Khối mới có giá trị khi thể hiện **một giai đoạn xử lý hợp lý**. Với logic phức tạp, tách thành phương thức có tên và tham số rõ ràng thường dễ bảo trì hơn.

## 7. Thu hẹp phạm vi bằng cách tách phương thức

Đây là cách thực tiễn khi một biến phải tồn tại trong một phương thức dài vì nhiều nhiệm vụ đang bị trộn vào nhau.

### Trước: một phương thức làm nhiều việc

```java
// Minh họa các bước: đầu vào, xử lý, tính tổng, hiển thị
var cleaned = new java.util.ArrayList<String>();
for (var raw : rawNames) {
    var name = raw.trim();
    if (!name.isEmpty()) {
        cleaned.add(name);
    }
}
var totalLength = 0;
for (var name : cleaned) {
    totalLength += name.length();
}
System.out.println(cleaned);
System.out.println(totalLength);
```

Đoạn trên không nhất thiết sai. Nhưng khi có nhiều bước phụ thêm, `cleaned` và `totalLength` có thể được dùng trải rộng, khiến việc suy luận kiểu và chỉnh sửa khó hơn.

### Sau: phân chia theo trách nhiệm

```java
static java.util.List<String> normalizeNames(java.util.List<String> rawNames) {
    var cleaned = new java.util.ArrayList<String>();
    for (var rawName : rawNames) {
        var name = rawName.trim();
        if (!name.isEmpty()) {
            cleaned.add(name);
        }
    }
    return cleaned;
}

static int countCharacters(java.util.List<String> names) {
    var total = 0;
    for (var name : names) {
        total += name.length();
    }
    return total;
}
```

Các phương thức trên là **thành viên của một lớp Java**, có thể đặt trong lớp chương trình ở mục 12. Ở nơi gọi:

```java
var cleanedNames = normalizeNames(rawNames);
var totalCharacters = countCharacters(cleanedNames);
System.out.println(cleanedNames);
System.out.println(totalCharacters);
```

Kết quả:

- `rawName` và `name` chỉ có nghĩa trong một vòng lặp ngắn.
- `cleaned` chỉ cần trong phương thức chuẩn hóa; `total` chỉ cần trong phương thức đếm.
- Giao diện của phương thức vẫn có kiểu **`List<String>`** và **`int`** tường minh, giúp người gọi hiểu hợp đồng. `var` phù hợp với các bước cục bộ.
- Khi mã tăng lên, người đọc có thể mở riêng phương thức liên quan, ít phải giữ trong đầu các biến không phục vụ nhiệm vụ hiện tại.

**Không biến việc tách hàm thành mục tiêu tự thân:** chỉ tách khi việc đặt tên nhiệm vụ, giảm phụ thuộc hoặc thu hẹp phạm vi mang lại lợi ích thực tế.

## 8. Dùng tên biến truyền đạt vai trò và kiểu suy luận

Khi vế trái chỉ còn `var`, tên biến thường là dấu hiệu đầu tiên về ý nghĩa giá trị.

Kém rõ:

```java
var x = users.stream().filter(User::active).toList();
var y = x.size();
```

Rõ hơn:

```java
var activeUsers = users.stream().filter(User::active).toList();
var activeUserCount = activeUsers.size();
```

Hai khối là **minh họa riêng**, giả sử lớp `User` có phương thức `active()` và `users` là danh sách phù hợp. `Stream.toList()` có từ Java 16, vì vậy đoạn cụ thể này dùng trên Java 17+ như đã nêu.

Tên `activeUsers` mô tả **vai trò của tập dữ liệu**, `activeUserCount` mô tả **ý nghĩa số lượng**. Không cần cố nhồi tên kiểu chính xác `ArrayList`, `Stream` hoặc `String` vào mọi tên biến. Ưu tiên tên giúp người đọc hiểu dữ liệu được dùng để làm gì.

Trong một vòng lặp rất ngắn, `i` có thể đủ rõ làm chỉ số; với biến truyền qua nhiều phép biến đổi, tên giàu ý nghĩa quan trọng hơn.

## 9. Chia biểu thức dài thành các bước nhỏ

Đôi khi code chỉ có một biểu thức dài khiến việc đọc luồng dữ liệu khó, trong khi khai báo nhiều kiểu tường minh sẽ làm mã rối. `var` có thể giúp đặt tên cho **biến trung gian ngắn hạn**:

```java
var frequencyByName = names.stream()
        .collect(java.util.stream.Collectors.groupingBy(
                name -> name,
                java.util.stream.Collectors.counting()));

var mostFrequentEntry = frequencyByName.entrySet().stream()
        .max(java.util.Map.Entry.comparingByValue());

var mostFrequentName = mostFrequentEntry
        .map(java.util.Map.Entry::getKey)
        .orElse("(none)");
```

Đoạn này **minh họa trong một phương thức**, giả sử `names` là `List<String>`. Mục đích là làm rõ ba bước có tên: thống kê tần suất, chọn mục có tần suất lớn nhất và lấy tên. `frequencyByName` có kiểu `Map<String, Long>`, `mostFrequentEntry` là một `Optional` chứa entry tương ứng, còn `mostFrequentName` có kiểu `String`.

Lưu ý nếu nhiều tên cùng đạt tần suất cao nhất, ví dụ không quy định tên nào sẽ được chọn vì không thêm quy tắc phá hòa. Nếu nghiệp vụ yêu cầu kết quả ổn định, cần định nghĩa cách chọn khi hòa.

**Giữ biến trung gian trong phạm vi nhỏ của giai đoạn xử lý.** `var` giúp tách ý tưởng, nhưng đặt tất cả biến ở đầu một phương thức dài rồi dùng rải rác sẽ làm mất lợi ích này.

## 10. Khi thay initializer: phạm vi ngắn giúp phát hiện tác động

Giả sử bạn muốn loại các giá trị trùng lặp trong danh sách:

```java
var names = new java.util.ArrayList<String>(
        java.util.List.of("An", "Binh"));
names.add("Lan");
System.out.println(names);
```

Nếu đổi initializer thành `new HashSet<String>(...)`, kiểu tĩnh của `names` đổi từ `ArrayList<String>` thành `HashSet<String>`. Hai cấu trúc khác nhau về khả năng giữ phần tử trùng và đặc tính thứ tự duyệt. Với `HashSet`, **không được dựa vào thứ tự in**.

Nếu ba dòng liền nhau, người review dễ phát hiện thay đổi có thể ảnh hưởng tới việc in hoặc xử lý theo thứ tự. Nhưng nếu phép `names.add(...)` hay vòng lặp sử dụng `names` nằm ở cuối phương thức dài, hậu quả ít hiển nhiên hơn.

Một cách thể hiện ý định khi **cần giữ thứ tự xuất hiện và loại trùng** là dùng `LinkedHashSet<String>`, có quy tắc duyệt theo thứ tự chèn. Khi **cần danh sách cho phép trùng**, giữ `ArrayList`. Việc chọn collection phải dựa trên yêu cầu nghiệp vụ, không chỉ độ ngắn của khai báo.

### Cẩn thận với generic `<>`

```java
var names = new java.util.ArrayList<>(); // ArrayList<Object>
```

Initializer không cung cấp kiểu phần tử, nên generic có thể suy luận `Object`. Dù phạm vi ngắn giúp nhận ra rủi ro nhanh, nó không làm kiểu biến trở thành `ArrayList<String>`. Nếu cần dữ liệu chuỗi, viết:

```java
var names = new java.util.ArrayList<String>();
// hoặc
java.util.List<String> names2 = new java.util.ArrayList<>();
```

Đây là lý do **phạm vi nhỏ và kiểu đúng** phải đi cùng nhau; một biến được đặt gần nơi sử dụng vẫn có thể mang kiểu suy luận không như mong muốn.

## 11. Khi nào giữ kiểu tường minh thay vì cố thu hẹp phạm vi?

Giới hạn phạm vi là hướng dẫn tốt, nhưng không phải lý do để dùng `var` trong mọi trường hợp:

- **API không gợi được kiểu:** `var result = gateway.execute();` có thể quá mơ hồ; kiểu tường minh hoặc tên phương thức/biến rõ hơn sẽ giúp review.
- **Hợp đồng interface quan trọng:** `List<String> names = new ArrayList<>();` làm rõ code chỉ muốn phụ thuộc vào `List` và cho phép thay implementation.
- **Generic hoặc wildcard không hiển nhiên:** dùng kiểu tường minh khi người đọc cần biết chính xác `List<? extends Number>`, `Map<String, List<Order>>` hoặc kiểu trả về API.
- **Kiểu số mang ý nghĩa:** `long timeoutMillis = 1000;` không tương đương hoàn toàn với `var timeoutMillis = 1000;` vì initializer sau suy luận `int`.
- **Phương thức quá dài không thể cải thiện ngay:** nếu một biến vẫn phải dùng xuyên nhiều đoạn code, kiểu tường minh có thể giữ thông tin gần người đọc ở dòng khai báo; sau đó cân nhắc refactor cấu trúc.

Cách chọn tốt thường là phối hợp: **kiểu tường minh ở ranh giới dữ liệu**, `var` cho các biến cục bộ ngắn và initializer đủ rõ.

## 12. Ví dụ Java 17+ biên dịch và chạy độc lập

Tạo tệp **`VarScopeDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class VarScopeDemo {
    // Kiểu trả về tường minh thể hiện hợp đồng của phương thức.
    static List<String> normalizeNames(List<String> rawNames) {
        var normalized = new ArrayList<String>();

        // originalName và cleanName chỉ phục vụ một vòng lặp ngắn.
        for (var originalName : rawNames) {
            var cleanName = originalName.trim();
            if (!cleanName.isEmpty()) {
                normalized.add(cleanName);
            }
        }
        return normalized;
    }

    static int totalLength(List<String> names) {
        var total = 0; // int, chỉ dùng trong phương thức đếm
        for (var name : names) {
            total += name.length();
        }
        return total;
    }

    public static void main(String[] args) throws IOException {
        var names = normalizeNames(
                List.of(" Lan ", "An", "  Binh ", "Lan "));
        System.out.println("names=" + names);

        // Khối con giới hạn phạm vi biến firstName.
        {
            var firstName = names.get(0);
            System.out.println("first=" + firstName);
        }

        // Chỉ số và biến phần tử có phạm vi thuộc vòng lặp.
        for (var index = 0; index < names.size(); index++) {
            var name = names.get(index);
            System.out.println("item[" + index + "]=" + name);
        }

        System.out.println("characters=" + totalLength(names));

        // Biến resource chỉ cần trong try-with-resources.
        try (var reader = new BufferedReader(new StringReader("ready"))) {
            var line = reader.readLine();
            System.out.println("line=" + line);
        }

        var longestName = names.stream()
                .max(Comparator.comparingInt(String::length))
                .orElse("");
        System.out.println("longest=" + longestName);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 VarScopeDemo.java
java VarScopeDemo
```

**Stdout chính xác:**

```text
names=[Lan, An, Binh, Lan]
first=Lan
item[0]=Lan
item[1]=An
item[2]=Binh
item[3]=Lan
characters=12
line=ready
longest=Binh
```

### Giải thích theo khả năng đọc mã

1. `normalizeNames` và `totalLength` thể hiện hai trách nhiệm riêng qua tên và kiểu trả về tường minh, nên biến trung gian không lan sang bước khác.
2. `originalName` và `cleanName` đều là `String`; người đọc nhìn ngay được nguồn từ `List<String>` và thao tác `trim()`.
3. `firstName` có kiểu `String` và chỉ cần trong một khối nhỏ; ra ngoài khối sẽ không còn truy cập được.
4. `index` là `int`; nó và `name` được giới hạn bởi vòng `for`, tránh lạm dụng biến đếm xuyên phương thức.
5. `reader` có kiểu `BufferedReader` và gắn với tài nguyên cần đóng; `line` là `String` nhận được từ `readLine()`.
6. `longestName` có kiểu `String` vì `max(...).orElse("")` trả về phần tử kiểu `String`. Tập dữ liệu có tên `Binh` dài nhất nên kết quả xác định.
7. Các biến đều được khai báo gần chỗ dùng, giúp kiểm tra initializer và hành vi mà không cần dò qua nhiều đoạn không liên quan.

## 13. Những lỗi và hiểu lầm thường gặp

### Lỗi A: Tưởng phạm vi ngắn làm biến trở thành kiểu động

```java
{
    var count = 1;  // int
    count = 2;      // hợp lệ
    // count = "2"; // lỗi: String không gán cho int
}
```

Phạm vi nhỏ giúp đọc dễ hơn, **không thay đổi hệ thống kiểu của Java**. Kiểu tĩnh vẫn được suy luận duy nhất tại khai báo.

### Lỗi B: Đưa khai báo ra trước vòng lặp khi không cần

```java
var i = 0;
for (; i < 3; i++) {
    System.out.println(i);
}
// i vẫn nằm trong phạm vi của khối chứa khai báo
```

Cách gọn hơn khi bộ đếm chỉ dùng ở vòng lặp:

```java
for (var i = 0; i < 3; i++) {
    System.out.println(i);
}
// i ngoài phạm vi
```

Cả hai đều hợp lệ. Sự khác biệt là **phạm vi của `i`**, không phải giá trị in ra (đều in `0`, `1`, `2`).

### Lỗi C: Dùng biến vòng lặp ở ngoài vòng

```java
for (var name : java.util.List.of("An", "Binh")) {
    System.out.println(name);
}
// System.out.println(name); // lỗi biên dịch: không có name trong phạm vi này
```

Nếu cần giá trị sau vòng lặp, hãy thiết kế biến tổng hợp với **kiểu và ý nghĩa rõ ràng** (ví dụ `String lastName`) ngoài vòng lặp, thay vì mong `name` “tồn tại tiếp”.

### Lỗi D: Vô tình thay đổi hành vi khi dời initializer

```java
var snapshot = list.size();
list.add("new");
System.out.println(snapshot); // số phần tử cũ, theo thời điểm snapshot được tính
```

Dời `var snapshot = list.size();` xuống sau `list.add("new")` làm giá trị thay đổi. Khi thu hẹp phạm vi, phải phân biệt **snapshot của trạng thái cũ** với **giá trị cần tính tại thời điểm sử dụng**.

### Lỗi E: Dùng tên quá mơ hồ

```java
var x = repository.findAll();
```

Khi `repository` và phương thức không được thấy trong ngữ cảnh gần, `x` không truyền đạt nội dung. Tên như `activeOrders` hoặc `customerIds` hữu ích hơn nếu đúng với giá trị thực; khi kiểu return phức tạp, có thể dùng kiểu tường minh.

### Lỗi F: Cố thu hẹp scope bằng ngoặc khiến code bị chia vụn

Nhiều khối `{ ... }` chỉ chứa một lệnh khiến người đọc khó theo dõi luồng chính. Ưu tiên phương thức có tên hoặc nhóm thao tác thực sự liên quan thay vì thêm ngoặc tùy tiện.

### Lỗi G: Dùng `final var` thay cho giới hạn scope

`final var names = new ArrayList<String>();` chỉ **cấm gán lại biến `names`**, không thu hẹp phạm vi cú pháp và không làm đối tượng `ArrayList` tự trở thành bất biến. `final` và phạm vi phục vụ hai mục đích khác nhau.

## 14. Checklist refactor: giới hạn phạm vi mà vẫn giữ đúng hành vi

Đọc từng biến `var` theo trình tự:

1. **Xác định initializer và kiểu suy luận thật.** Nếu là lời gọi phương thức, tra chữ ký trả về; nếu generic `<>`, kiểm tra kiểu phần tử.
2. **Tìm lần sử dụng đầu tiên và cuối cùng.** Biến có đang tồn tại qua nhiều nhánh không liên quan hay không?
3. **Dời khai báo gần nơi dùng nếu an toàn.** Kiểm tra side effect, ngoại lệ, snapshot dữ liệu và thứ tự thực thi trước/sau.
4. **Ưu tiên vùng phạm vi tự nhiên.** Dùng biến chỉ số ở `for`, phần tử ở enhanced `for`, resource trong `try`, biến nhánh trong khối nhánh.
5. **Tách phương thức khi trách nhiệm lớn.** Giao diện phương thức giữ kiểu tường minh, còn biến tính toán cục bộ có thể dùng `var`.
6. **Đặt tên theo vai trò và kết quả.** Ví dụ `normalizedNames`, `totalCharacters` và `longestName`.
7. **Kiểm tra tác động khi initializer đổi.** So sánh kiểu trước/sau, overload, phương thức khả dụng, thứ tự duyệt và generic.
8. **Biên dịch và chạy test phù hợp.** Kiểm tra các ví dụ và trường hợp biên như danh sách rỗng, `null` nếu API cho phép, hoặc nhiều phần tử trùng.
9. **Review mã khi không có IDE.** Người khác có dễ tìm initializer và theo dõi dữ liệu trong diff không? Nếu không, cân nhắc thu hẹp thêm hoặc hiện rõ kiểu.

Không cần quy định máy móc rằng một biến chỉ được tồn tại đúng 5 hay 10 dòng. **Số bước suy luận và mức độ rõ của luồng dữ liệu** hữu ích hơn một ngưỡng dòng cố định.

## 15. Bài tập tự kiểm tra

Mỗi câu là một tình huống độc lập.

**Câu 1.** `var total = items.size();` ở đầu một phương thức dài, chỉ được dùng trong câu lệnh in ở cuối. Khi nào dời khai báo xuống gần câu lệnh in là an toàn?

**Câu 2.** Trong `for (var i = 0; i < 4; i++)`, `i` có kiểu gì? Có dùng được sau vòng lặp không?

**Câu 3.** `for (var name : List.of("An", "Binh"))` suy luận kiểu nào cho `name` và phạm vi của nó ra sao?

**Câu 4.** `var customers = service.load();` có phạm vi rất ngắn nhưng tên phương thức không cho biết kiểu. Có nên mặc định giữ `var` không?

**Câu 5.** Vì sao thay `new ArrayList<String>()` bằng `new HashSet<String>()` cần kiểm tra code phía sau ngay cả khi cả hai có thể được dùng như collection?

**Câu 6.** `var list = new ArrayList<>(); list.add("An");` có chắc `list` là `ArrayList<String>` không? Việc rút ngắn phạm vi có sửa được lỗi suy luận generic không?

**Câu 7.** `final var x = new ArrayList<String>();` có giúp `x` tự động mất hiệu lực sau một khối logic nhỏ không?

**Câu 8.** Khi có 30 dòng xử lý tên rồi 40 dòng thống kê, giải pháp nào giúp phạm vi `var` rõ ràng hơn: gom tất cả khai báo ở đầu phương thức hay tách các giai đoạn thành phương thức có tên?

**Đáp án:**

1. An toàn nếu những thao tác giữa hai vị trí không thay đổi dữ liệu cần đo, không làm khác side effect/ngoại lệ hoặc yêu cầu snapshot tại thời điểm cũ. Nếu `items` thay đổi, kết quả `size()` có thể khác.
2. Kiểu `int`; biến `i` trong initializer của basic `for` không dùng được sau vòng.
3. `name` là `String` từ phần tử `List<String>`; chỉ trong thân enhanced `for`.
4. Không mặc định. Cân nhắc kiểu tường minh, tên biến mạnh hơn hoặc API có tên/mô tả rõ ràng nếu người đọc không biết kiểu.
5. Vì loại collection, thứ tự duyệt, xử lý phần tử trùng và những phương thức cụ thể có thể thay đổi; `var` suy luận kiểu mới từ initializer.
6. Không. `new ArrayList<>()` không có dữ kiện `String` nên có thể suy luận `ArrayList<Object>`; cần `new ArrayList<String>()` hoặc khai báo `List<String>` tường minh.
7. Không. `final` chặn gán lại, nhưng không sửa phạm vi cú pháp; đối tượng có thể vẫn mutable.
8. Nên tách theo nhiệm vụ như `normalizeNames(...)` và `countCharacters(...)` hoặc tạo những khối có ý nghĩa. Mỗi nhóm biến có phạm vi gắn với nhiệm vụ của nó.

## 16. Ghi nhớ và tài liệu tham khảo

- **`var` suy luận kiểu tĩnh từ initializer**, không tạo biến kiểu động và không tự thay đổi quy tắc scope.
- **Giới hạn phạm vi tên biến và giảm khoảng cách từ khai báo đến sử dụng** giúp người đọc nhanh chóng tìm được initializer, kiểu và ý định.
- **Dùng cấu trúc sẵn có của ngôn ngữ** để giới hạn biến: khối, vòng `for`, enhanced `for` và `try-with-resources`.
- **Tách phương thức và đặt tên có ý nghĩa** có tác dụng lớn hơn việc rút ngắn cú pháp một cách cơ học.
- **Thu hẹp scope phải giữ nguyên hành vi cần thiết**: cẩn thận với snapshot, side effect, ngoại lệ, generic và thay đổi implementation.
- **Dùng kiểu tường minh khi cần diễn đạt hợp đồng**, đặc biệt ở phương thức, interface và generic khó suy luận.

Nguồn tham khảo vẫn có giá trị áp dụng:

1. [OpenJDK Project Amber – Local Variable Type Inference Style Guidelines](https://github.com/openjdk/amber-docs/blob/master/site/guides/lvti-style-guide.md): hướng dẫn **G1** đặt tên, **G2** giảm phạm vi, **G3** initializer rõ, **G4** tách biểu thức, **G5–G6** lưu ý interface và generic.
2. [OpenJDK – JEP 286: Local-Variable Type Inference](https://openjdk.org/jeps/286): quy tắc nền tảng của `var` từ Java 10.
3. [Java Language Specification SE 26 – `6.3: Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se26/html/jls-6.html#jls-6.3): phạm vi các biến cục bộ, `for` và resource.
4. [Java Language Specification SE 26 – `14.4: Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se26/html/jls-14.html#jls-14.4): suy luận kiểu từ initializer.
5. [Java Language Specification SE 26 – `14.20.3: try-with-resources](https://docs.oracle.com/javase/specs/jls/se26/html/jls-14.html#jls-14.20.3): phạm vi tài nguyên và đóng tài nguyên.
