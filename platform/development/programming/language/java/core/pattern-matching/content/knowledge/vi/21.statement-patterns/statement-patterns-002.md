# Pattern trong while statement (Java 21+)

## 1. Vì sao pattern matching hữu ích trong vòng lặp `while`?

Vòng lặp `while` thường đọc dữ liệu từng bước: lấy phần tử từ một luồng, duyệt các nút liên kết, hoặc tiếp tục xử lý chừng nào dữ liệu còn đúng kiểu. Khi dùng cách kiểm tra kiểu truyền thống, ta phải viết `instanceof`, ép kiểu và kiểm tra giá trị ở các vị trí riêng:

~~~java
Object current = "Java";

while (current instanceof String) {
    String text = (String) current;
    System.out.println(text.toUpperCase());
    current = 42; // Thay đổi trạng thái để vòng lặp có thể kết thúc
}
~~~

Với **type pattern** (`String text`), điều kiện `while` có thể vừa kiểm tra kiểu vừa tạo biến đã được kiểm tra kiểu:

~~~java
Object current = "Java";

while (current instanceof String text) {
    System.out.println(text.toUpperCase());
    current = 42;
}
~~~

Trong ví dụ sau, Java biết `text` có kiểu `String` **bên trong thân vòng lặp**, vì thân chỉ chạy sau khi điều kiện `instanceof String text` đúng. Không còn phép ép kiểu tường minh.

Điểm khác biệt của `while` so với một phép `if` thông thường là **điều kiện được đánh giá lại trước mỗi lần lặp**. Java có thể tạo giá trị mới cho biến mẫu ở mỗi lượt khớp; nếu điều kiện không còn khớp, thân vòng lặp không thực thi ở lượt đó.

Type pattern với `instanceof` đã là tính năng chính thức từ Java 16. **Record pattern** trong `while` (ví dụ `Link(String name, var next)`) được chuẩn hóa ở Java 21; bài này dùng **JDK 21+** để trình bày cả hai.

## 2. Cơ chế: kiểm tra trước, tạo biến sau khi khớp

Cú pháp cốt lõi:

~~~java
while (expression instanceof SomeType variable) {
    // variable có kiểu SomeType và có thể dùng ở đây
    // Cập nhật trạng thái được kiểm tra để vòng lặp có thể tiến triển
}
~~~

Ba bước xảy ra theo thứ tự:

1. Java đánh giá toàn bộ điều kiện `while`. Biểu thức `instanceof` với type pattern trả về `false` khi giá trị là `null` hoặc không thuộc kiểu phù hợp.
2. Nếu mẫu khớp và toàn bộ điều kiện đúng, biến mẫu được gắn với giá trị đã khớp. Thân vòng lặp được chạy và **biến có phạm vi sử dụng hợp lệ** tại đó.
3. Sau thân vòng lặp, Java quay lại kiểm tra điều kiện. Nếu lần này không còn khớp, vòng lặp kết thúc.

Biến mẫu tuân theo **phạm vi theo luồng điều khiển** (*flow scoping*). Việc tên biến xuất hiện trong phần điều kiện không có nghĩa nó dùng được ở mọi dòng phía sau biểu thức `while`.

~~~java
Object input = "hello";

while (input instanceof String text) {
    System.out.println(text.length()); // Hợp lệ
    input = null;
}

// System.out.println(text); // Lỗi biên dịch nếu bỏ comment
~~~

Sau vòng lặp với **mẫu khẳng định** `input instanceof String text`, điều kiện có thể đã trở thành `false`; vì vậy không thể dùng `text` ở dòng sau. Đây là **đoạn minh họa** độc lập trong một phương thức có khai báo `input` như trên.

Cần phân biệt việc một biến mẫu có **kiểu tĩnh rõ ràng** với việc đối tượng nguồn có thể đổi kiểu ở lần lặp sau: `text` là `String` trong thân lặp hiện tại, còn biến `input` vẫn có kiểu khai báo `Object`.

## 3. Ghép pattern với các điều kiện khác bằng `&&`

Một điều kiện `while` thường không chỉ kiểm tra kiểu. Ta có thể kiểm tra đồng thời độ dài, nội dung, giới hạn chỉ số và các quy tắc khác:

~~~java
Object[] items = {"java", "21", 42, "after"};
int index = 0;

while (index < items.length
        && items[index] instanceof String word
        && !word.isBlank()) {
    System.out.println(word);
    index++;
}
~~~

Kết quả:

~~~text
java
21
~~~

Ở chỉ số `2`, giá trị là số nguyên `42` nên mẫu `String word` không khớp; vòng lặp dừng. Phần tử `"after"` phía sau **không được xử lý**.

Thứ tự ba điều kiện mang ý nghĩa quan trọng:

- `index < items.length` phải đúng trước khi truy cập `items[index]`; điều này tránh truy cập ngoài mảng.
- `items[index] instanceof String word` phải khớp trước khi gọi phương thức trên `word`.
- `!word.isBlank()` chỉ được đánh giá sau khi mẫu đã khớp, do `&&` chạy **ngắn mạch từ trái sang phải**.

Nhờ đó, `word` có phạm vi hợp lệ ở vế `!word.isBlank()` và bên trong thân `while`.

Một cách viết **cố ý sai**:

~~~java
// KHÔNG BIÊN DỊCH: vế phải của || có thể chạy khi mẫu bên trái thất bại.
while (items[index] instanceof String word || word.isBlank()) {
    // ...
}
~~~

Với `||` ở biểu thức trên, Java có thể phải đánh giá `word.isBlank()` khi mẫu bên trái không khớp, nên `word` chưa được bảo đảm có giá trị. Ngoài ra còn thiếu kiểm tra biên cho `index`. Khi cần lựa chọn giữa nhiều trường hợp khác nhau, hãy dùng một cấu trúc điều kiện rõ ràng; đừng thay `&&` bằng `||` chỉ để gộp các biểu thức.

## 4. Vòng lặp phải có bước tiến để kết thúc

Pattern matching **không tự làm cho vòng lặp tiến triển**. Ví dụ sau có thể chạy vô hạn:

~~~java
Object input = "A";

// SAI về thuật toán: input không đổi sau mỗi lần lặp.
while (input instanceof String text) {
    System.out.println(text);
}
~~~

Mẫu luôn khớp vì `input` luôn chứa cùng một chuỗi. Để tránh lỗi này, hãy xác định rõ **đại lượng thay đổi qua mỗi lần lặp**: chỉ số tăng, iterator tiến đến phần tử tiếp theo, hoặc biến trỏ tới nút kế tiếp.

Cách sửa một vòng lặp duyệt mảng:

~~~java
Object[] values = {"A", "B", 10};
int index = 0;

while (index < values.length && values[index] instanceof String text) {
    System.out.println(text);
    index++; // Tiến tới phần tử tiếp theo
}
~~~

Đoạn trên dừng khi gặp `10`. Khi sử dụng `continue`, bước cập nhật phải xảy ra **trước** câu lệnh `continue` hoặc ở một vị trí chắc chắn được chạy trong mọi nhánh cần tiếp tục; nếu không, rất dễ lặp mãi trên cùng một phần tử.

Dùng `while (iterator.hasNext() && iterator.next() instanceof String text)` cũng cần thận trọng: `next()` tiêu thụ một phần tử **ngay cả khi mẫu không khớp**. Nếu cần giữ lại hoặc xử lý riêng phần tử đầu tiên không hợp lệ, hãy lấy ra biến `current` trong thân vòng lặp và chủ động quyết định cách xử lý.

## 5. Phân biệt “dừng ở phần tử không khớp” và “bỏ qua phần tử không khớp”

Đây là một quyết định nghiệp vụ, không chỉ là cách viết code.

**Cách A — pattern nằm trong điều kiện `while`:** vòng lặp xử lý một **đoạn đầu liên tiếp** của các phần tử phù hợp và dừng ngay tại phần tử đầu tiên không khớp.

~~~java
int index = 0;
while (index < items.length && items[index] instanceof String word) {
    System.out.println(word);
    index++;
}
~~~

Với dữ liệu `{"java", "21", 42, "after"}`, chỉ `"java"` và `"21"` được in. Phần tử `42` khiến điều kiện sai và không có lượt tiếp theo.

**Cách B — `while` kiểm tra khả năng tiếp tục duyệt, còn pattern nằm trong thân:** vòng lặp có thể bỏ qua giá trị không hợp lệ và vẫn xem phần tử tiếp theo.

~~~java
int index = 0;
while (index < items.length) {
    Object item = items[index++];

    if (!(item instanceof String word)) {
        continue; // Chỉ bỏ qua phần tử hiện tại
    }
    System.out.println(word);
}
~~~

Với dữ liệu trên, cách B in thêm `"after"`. Nhờ đặt `index++` trước `continue`, phần tử hiện tại luôn được tiêu thụ, tránh lặp vô hạn.

Hai cách viết phục vụ hai yêu cầu **khác nhau**:

| Yêu cầu | Cấu trúc phù hợp |
| --- | --- |
| Duyệt liên tiếp khi phần tử tiếp theo còn đúng kiểu | Đặt type pattern trong điều kiện `while` |
| Duyệt hết nguồn, bỏ qua phần tử sai kiểu | Đặt pattern trong thân `while` và dùng `continue` |
| Báo lỗi ngay khi gặp dữ liệu sai | Dùng `if (!(...))` rồi `throw` hoặc trả kết quả lỗi |
| Cần xử lý riêng phần tử đầu tiên không khớp | Không tiêu thụ mù phần tử trong điều kiện `while` |

Trong thực tế, chọn cấu trúc theo ý nghĩa của dữ liệu: “đọc prefix liên tiếp” khác với “lọc toàn bộ danh sách”.

## 6. Record pattern trong `while`: duyệt cấu trúc lồng nhau

Từ Java 21, điều kiện `while` cũng có thể phân rã một `record`:

~~~java
record Link(String name, Link next) {}
~~~

`Link` lưu tên và con trỏ đến nút tiếp theo. Có thể duyệt danh sách liên kết đơn giản mà không cần gọi `link.name()` và `link.next()` ở hai bước riêng:

~~~java
Object cursor = new Link("A", new Link("B", null));

while (cursor instanceof Link(String name, var next)
        && !name.isBlank()) {
    System.out.println("link=" + name);
    cursor = next;
}
~~~

Kết quả:

~~~text
link=A
link=B
~~~

Giải thích:

- `Link(String name, var next)` là **record pattern** gồm hai component pattern tương ứng với `name` và `next` của record `Link`.
- `String name` yêu cầu component `name` có giá trị `String` khác `null`. `var next` suy ra kiểu `Link` từ khai báo record; nó **có thể** nhận `null`.
- Mỗi lượt, `cursor = next` tiến sang nút sau. Đến cuối, `cursor == null` nên `instanceof Link(...)` sai và vòng lặp kết thúc.
- `!name.isBlank()` còn đặt thêm quy tắc dừng ở tên rỗng hoặc toàn khoảng trắng. Nó được đánh giá khi `name` đã khớp mẫu `String`.
- Nếu một `Link` có `name == null`, mẫu `String name` không khớp nên thân lặp không được chạy cho nút đó. Nếu thay bằng `var name`, mẫu có thể nhận `null` và phải kiểm tra `name != null` trước khi gọi `name.isBlank()`.

Cách duyệt này phù hợp khi toàn bộ chuỗi nút có cấu trúc rõ. Với hệ thống dùng danh sách liên kết do người dùng cung cấp, cũng cần tính tới **chu kỳ** (một nút trỏ trở lại nút trước): pattern không tự phát hiện chu kỳ, nên phải có giới hạn hoặc cơ chế nhận diện nút đã duyệt nếu dữ liệu không bảo đảm kết thúc.

## 7. Trường hợp nâng cao: mẫu phủ định và biến sau vòng lặp

Flow scoping có một trường hợp đáng chú ý. Khi điều kiện `while` yêu cầu **mẫu chưa khớp**, rồi thân lặp biến đổi dữ liệu đến khi mẫu khớp, biến mẫu có thể dùng được **sau khi vòng lặp kết thúc bình thường**:

~~~java
static String normalize(Object candidate) {
    while (!(candidate instanceof String text)) {
        candidate = "ready";
    }
    return text.toUpperCase(java.util.Locale.ROOT);
}
~~~

- Vòng lặp chỉ tiếp tục khi `candidate` **chưa** khớp `String text`.
- Khi vòng lặp kết thúc do điều kiện trở thành `false`, tức `candidate instanceof String text` đã khớp.
- Java có thể chứng minh `text` có giá trị ở lệnh `return` phía sau; ví dụ `normalize(5)` trả về `"READY"`.

Đây là **phương thức minh họa**, được dùng nguyên vẹn trong chương trình hoàn chỉnh ở mục 8.

Quy tắc này khác với `while (candidate instanceof String text)`: sau vòng lặp khẳng định, mẫu có thể thất bại nên biến `text` **không** còn dùng được. Ngoài ra, **không thêm nhánh `break`** vào vòng lặp phủ định rồi giả định `text` vẫn chắc chắn tồn tại. `break` có thể rời vòng lặp trước khi mẫu khớp, khiến trình biên dịch không thể bảo đảm biến mẫu đã được gán ở phía sau.

Trường hợp phủ định thường hữu ích khi vòng lặp thật sự có nhiệm vụ **tìm/biến đổi cho đến khi gặp dữ liệu đúng kiểu**. Không nên dùng nó để tạo một chu trình vô hạn chỉ với hy vọng dữ liệu sẽ tự thay đổi; điều kiện thoát vẫn phải được xác định rõ.

## 8. Chương trình Java 21 hoàn chỉnh

Chương trình sau minh họa bốn tình huống: dừng ở giá trị đầu tiên sai kiểu, bỏ qua giá trị sai kiểu, duyệt record có nút kế tiếp và sử dụng biến mẫu sau vòng lặp phủ định.

Tạo tệp **`WhilePatternDemo.java`**:

~~~java
public class WhilePatternDemo {
    record Link(String name, Link next) {}

    static void prefix(Object[] items) {
        int index = 0;
        while (index < items.length
                && items[index] instanceof String word
                && !word.isBlank()) {
            System.out.println("prefix=" + word);
            index++;
        }
        System.out.println("stopIndex=" + index);
    }

    static void filter(Object[] items) {
        int index = 0;
        while (index < items.length) {
            Object item = items[index++];
            if (!(item instanceof String word)) {
                continue;
            }
            if (word.isBlank()) {
                continue;
            }
            System.out.println("filtered=" + word);
        }
    }

    static void walk(Object first) {
        Object cursor = first;
        int visited = 0;
        while (cursor instanceof Link(String name, var next)
                && !name.isBlank()) {
            System.out.println("link=" + name);
            visited++;
            cursor = next;
        }
        System.out.println("linksVisited=" + visited);
    }

    static String normalize(Object candidate) {
        while (!(candidate instanceof String text)) {
            candidate = "ready";
        }
        return text.toUpperCase(java.util.Locale.ROOT);
    }

    public static void main(String[] args) {
        Object[] samples = {"java", "21", 42, "after", null, " "};

        prefix(samples);
        filter(samples);
        walk(new Link("A", new Link("B", null)));
        System.out.println("normalized=" + normalize(5));
    }
}
~~~

Biên dịch và chạy bằng **JDK 21+**:

~~~bash
javac --release 21 WhilePatternDemo.java
java WhilePatternDemo
~~~

Kết quả:

~~~text
prefix=java
prefix=21
stopIndex=2
filtered=java
filtered=21
filtered=after
link=A
link=B
linksVisited=2
normalized=READY
~~~

### Phân tích output

1. `prefix` xử lý hai chuỗi đầu, rồi dừng tại `42` với `index == 2`. Chuỗi `"after"` không được duyệt trong hàm này.
2. `filter` quét toàn bộ mảng. Nó bỏ qua `42` và `null` vì không khớp `String word`, bỏ qua `" "` vì `isBlank()` đúng, nhưng vẫn in chuỗi `"after"`.
3. `walk` phân rã lần lượt hai record `Link`. Nút thứ hai có `next == null` nên vòng lặp dừng sau hai lượt.
4. `normalize` nhận số `5`, chuyển sang chuỗi `"ready"` ở lượt lặp đầu, rồi kết thúc khi pattern khớp; nó dùng được biến `text` phía sau nên in `"READY"`.

Chương trình này **độc lập**, gồm các kiểu record, phương thức và `main` trong một tệp. Các đoạn cố ý sai ở phần khác chỉ nhằm giải thích lỗi và **không xuất hiện** trong tệp biên dịch được.

## 9. Kiểm thử các trường hợp biên

Khi dùng pattern trong điều kiện `while`, không chỉ chạy trường hợp tất cả giá trị đều đúng kiểu. Nên kiểm tra các tình huống sau:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Phần tử đầu tiên đã sai kiểu | Thân vòng lặp dùng mẫu khẳng định không chạy lượt nào |
| Phần tử giữa danh sách sai kiểu | Vòng lặp duyệt prefix dừng ngay; vòng lặp filter có thể bỏ qua và tiếp tục |
| Giá trị đầu vào `null` | `instanceof` không khớp; không dereference biến mẫu |
| Phần tử là `String` rỗng hoặc trắng | Type pattern khớp, nhưng guard `!word.isBlank()` làm điều kiện sai |
| Chỉ số đạt độ dài mảng | `index < items.length` sai, truy cập `items[index]` không được đánh giá |
| Nút record có `next == null` | Duyệt hết nút hiện tại rồi dừng ở lượt kiểm tra tiếp theo |
| Nút record có `name == null` | `Link(String name, var next)` không khớp tại nút đó |
| Nguồn không đổi trong thân vòng lặp | Có nguy cơ lặp vô hạn nếu mẫu luôn đúng |
| Dùng `continue` trước bước cập nhật | Có nguy cơ xét lặp lại cùng phần tử |
| Dùng `break` trong vòng lặp có mẫu phủ định | Không được mặc định biến mẫu đã khớp sau `break` |

Các bài toán có nguồn dữ liệu biến đổi hoặc chịu tác động từ thread khác cần được kiểm thử thêm theo cơ chế đồng bộ riêng. Flow scoping chỉ bảo đảm phạm vi và kiểu của biến mẫu tại đường thực thi hợp lệ; nó **không** thay thế kiểm soát trạng thái đồng thời.

## 10. Các lỗi phổ biến

**Lỗi 1 — nhầm phạm vi biến mẫu.** `word` tồn tại ở thân `while` khi mẫu khẳng định khớp; đừng sử dụng `word` phía sau vòng lặp như một biến luôn có giá trị. Trường hợp mẫu phủ định có thể tạo phạm vi sau vòng lặp khi điều kiện thoát chứng minh được mẫu đã khớp, nhưng cần xét từng đường đi điều khiển.

**Lỗi 2 — không cập nhật giá trị kiểm tra.** `while (object instanceof String s)` có thể lặp mãi nếu `object` không đổi. Chỉ số, iterator hoặc nút hiện tại phải tiến tới trạng thái mới.

**Lỗi 3 — đọc vượt phạm vi của mảng.** Đặt kiểm tra biên **trước** phép truy cập `items[index]` trong chuỗi `&&`.

**Lỗi 4 — đổi `&&` thành `||` không xét đường đi.** Với `pattern || usePatternVariable`, biến mẫu có thể chưa được tạo tại vế phải. Việc chọn toán tử phụ thuộc logic cần biểu diễn và các bảo đảm của flow scoping.

**Lỗi 5 — tưởng `instanceof` tự lọc được mọi quy tắc nghiệp vụ.** `String word` kiểm tra kiểu; điều kiện không trắng, độ dài hay định dạng cần được đặt thêm. Record pattern kiểm tra cấu trúc; nó không tự xác nhận toàn bộ tính hợp lệ của dữ liệu.

**Lỗi 6 — cho rằng mọi component của record đều khác `null`.** Mẫu có `String name` không khớp khi `name == null`, nhưng `var next` có thể nhận `null`. Nếu dùng `var name`, hãy kiểm tra `name != null` trước lời gọi phương thức trên `name`.

**Lỗi 7 — bỏ qua phần tử đầu tiên không khớp dù nghiệp vụ muốn xử lý nó.** Dùng `iterator.next()` trong điều kiện `while` có thể tiêu thụ giá trị rồi dừng ngay. Nên tách bước lấy phần tử nếu cần xử lý lý do không hợp lệ.

**Lỗi 8 — đặt quá nhiều điều kiện trong một vòng lặp.** Nếu biểu thức dài, hãy chia thành hàm có tên, dùng `if` kiểm tra/`continue` trong thân hoặc tách bước duyệt khỏi bước xác nhận dữ liệu. Cú pháp ngắn chỉ có giá trị khi vẫn dễ đọc.

## 11. Bài tập tự luyện

**Bài tập A:** Với mảng `{"A", "B", 7, "C"}`, dự đoán số lần thân `while` chạy nếu pattern nằm trong điều kiện. Sau đó sửa chương trình để bỏ qua `7` và tiếp tục in `"C"` mà không bỏ sót phần tử nào.

**Bài tập B:** Thay phần tử đầu tiên bằng `null`. Kiểm tra sự khác nhau giữa phiên bản dừng khi không khớp và phiên bản lọc tất cả dữ liệu; giải thích vì sao `instanceof String word` không tạo biến mẫu cho giá trị `null`.

**Bài tập C:** Tạo `Link("A", new Link("", new Link("C", null)))`. Với guard `!name.isBlank()`, vòng lặp in những nút nào? Hãy đổi quy tắc để bỏ qua tên trắng nhưng vẫn đi tiếp đến `"C"` mà không làm mất bước cập nhật `cursor = next`.

**Bài tập D:** Sửa `normalize` để nhận giá trị `String` ban đầu. Kiểm tra rằng vòng lặp phủ định không chạy lần nào nhưng phương thức vẫn trả kết quả chuyển thành chữ hoa. Sau đó thử thêm một nhánh `break` vào thân và quan sát trình biên dịch phân tích phạm vi `text` ở câu lệnh `return`.

**Ghi nhớ:** Pattern trong điều kiện `while` cho phép **kiểm tra kiểu, tạo biến và kiểm tra guard** ngay tại điểm quyết định tiếp tục vòng lặp. Dùng `&&` theo thứ tự an toàn, cập nhật dữ liệu mỗi lượt, và chọn có chủ đích giữa **dừng khi không khớp** với **bỏ qua phần tử không khớp**. Với Java 21+, record pattern còn giúp duyệt cấu trúc record và truy cập các component trực tiếp mà vẫn tuân theo quy tắc flow scoping.