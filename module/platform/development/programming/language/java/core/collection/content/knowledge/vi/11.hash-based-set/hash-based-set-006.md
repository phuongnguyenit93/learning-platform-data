# Thêm lại phần tử có sẵn và thứ tự của LinkedHashSet

## 1. Vấn đề cần giải quyết: giữ thứ tự nào khi dữ liệu xuất hiện nhiều lần?

Giả sử chương trình ghi nhận các giai đoạn công việc theo thứ tự `draft → review → done`. Một sự kiện `review` lại được gửi đến. Bạn muốn loại bản trùng, nhưng thứ tự kết quả nên là `draft → review → done` hay `draft → done → review`?

Hai kết quả phục vụ hai yêu cầu khác nhau. Kết quả thứ nhất giữ vị trí của lần ghi nhận đầu tiên khi phần tử vẫn còn trong tập. Kết quả thứ hai phản ánh một lần xuất hiện gần đây hơn. Chỉ biết “tập không chứa phần tử trùng” chưa đủ để phân biệt chúng.

`LinkedHashSet` phù hợp khi bạn cần tập hợp không trùng cùng một thứ tự duyệt xác định. Với phương thức `add` thông thường, thêm một phần tử đã có **không đưa phần tử đó về cuối**. Lần gọi trả về `false` và vị trí cũ được giữ lại. Xóa phần tử rồi thêm lại là một chuỗi thao tác khác: phần tử thực sự rời tập, sau đó được thêm mới ở cuối.

Bài học tập trung vào ranh giới này: `add` trùng, xóa rồi thêm, thêm theo lô và đối tượng tương đương. Các ví dụ chính chỉ dùng API có trong Java 17. Phần cuối nêu riêng các phương thức định vị xuất hiện từ Java 21 để tránh áp dụng nhầm quy tắc của `add` cho mọi phương thức.

Bạn cần biết cách khai báo biến, gọi phương thức, dùng `List` và vòng lặp. Khái niệm `equals`, `hashCode`, thứ tự duyệt và ý nghĩa giá trị trả về sẽ được nhắc lại tại chỗ.

## 2. Ba câu hỏi phải tách riêng

Đứng trước một lần gọi `set.add(element)`, hãy hỏi lần lượt:

1. Trước lời gọi, tập đã có phần tử tương đương hay chưa?
2. Sau lời gọi, tập có thêm một thành viên không?
3. Thứ tự các thành viên khi duyệt thay đổi thế nào?

Câu thứ nhất quyết định đây là thêm mới hay thêm trùng. Câu thứ hai được phản ánh bằng giá trị `boolean` trả về. Câu thứ ba liên quan đến cam kết thứ tự của cách triển khai cụ thể.

Những thuật ngữ chính:

| Thuật ngữ | Ý nghĩa trong bài |
| --- | --- |
| Thành viên | Một phần tử hiện thuộc tập |
| Phần tử tương đương | Hai đối tượng được xem là cùng giá trị theo quy tắc bằng nhau của tập |
| Thứ tự duyệt | Trình tự nhận phần tử qua `iterator` hoặc vòng lặp `for-each` |
| Thứ tự chèn | Thứ tự những lần thêm mới thành công, có tính đến việc phần tử đã bị xóa |
| Đối tượng đại diện | Đối tượng thực tế đang được lưu cho một giá trị trong tập |
| Thứ tự truy cập | Thứ tự dựa vào các lần sử dụng gần đây; khác yêu cầu giữ vị trí khi thêm mới |

Một tập có thể có cùng các thành viên với tập khác mà duyệt ra thứ tự khác. Một đối tượng mới được tạo cũng có thể tương đương với đối tượng cũ. Vì vậy, không suy thứ tự từ số lượng phần tử và không suy “mới đối với tập” từ toán tử `new`.

## 3. Quy tắc của add trong LinkedHashSet

Với dữ liệu có quy tắc `equals/hashCode` hợp lệ và không bị sửa sai trong thời gian lưu, có thể đọc hành vi của `add` như sau:

| Trước `add(e)` | Giá trị trả về | Số phần tử | Thứ tự duyệt |
| --- | --- | --- | --- |
| Chưa có phần tử tương đương với `e` | `true` | Tăng một | `e` được thêm ở cuối |
| Đã có phần tử tương đương với `e` | `false` | Không đổi | Vị trí hiện có được giữ nguyên |

Tài liệu `LinkedHashSet` quy định rõ việc gọi lại `add` khi phần tử đã có không làm đổi thứ tự chèn. Đây là cam kết API, không phải kết quả tình cờ của một lần chạy. [Java 17: LinkedHashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html).

Đoạn minh họa dưới đây giả sử đã nhập `java.util.LinkedHashSet` và `java.util.List`:

~~~java
LinkedHashSet<String> stages =
        new LinkedHashSet<>(List.of("draft", "review", "done"));

boolean changed = stages.add("review");
System.out.println(changed);
System.out.println(stages);
~~~

Kết quả:

~~~text
false
[draft, review, done]
~~~

Không có vị trí mới cho `review`. Cũng không có bản `review` thứ hai bị ẩn ở cuối. Tập vẫn chứa đúng ba phần tử.

`false` không có nghĩa là “phần tử vắng mặt sau lời gọi”. Trong ví dụ, `review` đã có trước và vẫn có sau lời gọi. Nó biểu thị rằng lời gọi `add` không làm tập nhận thêm thành viên. Đừng dùng `if (!set.add(x))` như bằng chứng rằng `x` bị thất lạc.

Với `contains("draft")`, chương trình chỉ hỏi về sự hiện diện. Lời gọi không chuyển `draft` ra sau các phần tử khác. Do đó, cả việc thấy lại một giá trị qua `add` lẫn việc kiểm tra qua `contains` đều không biến tập thành danh sách “vừa dùng gần đây”.

## 4. Vì sao bảng băm vẫn đi cùng thứ tự chèn?

Tên `LinkedHashSet` biểu thị hai vai trò phối hợp:

- Phần băm hỗ trợ tìm xem giá trị đã có hay chưa.
- Các liên kết giữa phần tử hỗ trợ lần lượt duyệt theo thứ tự được duy trì.

Có thể hình dung dữ liệu hiện tại bằng sơ đồ đơn giản:

~~~text
Thành viên theo quy tắc bằng nhau: {draft, review, done}

Chuỗi phục vụ duyệt:
đầu → draft ⇄ review ⇄ done ← cuối
~~~

Sơ đồ không mô tả vị trí vật lý trong bộ nhớ hoặc số ngăn của bảng băm. Nó giúp phân biệt thao tác tìm thành viên với thao tác thay đổi chuỗi thứ tự.

Khi thêm một giá trị mới, tập tạo thêm sự hiện diện và nối nó vào cuối chuỗi. Khi giá trị đã tồn tại, không cần tạo một thành viên thứ hai để nối thêm. Việc tìm được thành viên cũ không tự mang ý nghĩa “chuyển thành viên này đến cuối”.

Trong OpenJDK 17, `HashSet` có một bảng ánh xạ làm nơi lưu phần tử; `LinkedHashSet` dùng biến thể dựa trên `LinkedHashMap` theo thứ tự chèn. Các phần tử của tập được lưu ở phía khóa. Vì vậy, hành vi thêm trùng có liên hệ với việc tìm thấy một khóa cũ, không phải xóa khóa rồi tạo lại. Đây là mô tả cách triển khai giúp giải thích kết quả; ứng dụng vẫn nên dựa vào hợp đồng API. [Mã nguồn HashSet, OpenJDK 17](https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/java.base/share/classes/java/util/HashSet.java).

Không cần biết công thức chọn ngăn băm để dự đoán ví dụ `draft/review/done`. Thứ tự chèn của `LinkedHashSet` được cam kết ở cấp API. Thay đổi dung lượng bảng hoặc có va chạm băm không phải lý do để ứng dụng chấp nhận thứ tự duyệt tùy ý.

## 5. Xóa rồi thêm lại tạo vị trí mới

So sánh hai chuỗi thao tác trên trạng thái ban đầu `[draft, review, done]`.

Trường hợp A:

~~~text
add(review) → false
kết quả     → [draft, review, done]
~~~

Trường hợp B:

~~~text
remove(review) → true
trạng thái     → [draft, done]
add(review)    → true
kết quả        → [draft, done, review]
~~~

Ở trường hợp B, khi gọi `add`, tập không còn `review`. Lời gọi đó là thêm mới đối với trạng thái hiện tại, dù chương trình từng chứa cùng giá trị trong quá khứ.

Cách hiểu “thứ tự lần đầu xuất hiện” cần có giới hạn này. `LinkedHashSet` không lưu vĩnh viễn vị trí lịch sử của những phần tử đã xóa. Nếu xóa `review` rồi thêm lại, tập không tự đưa nó về giữa `draft` và `done`.

Cũng cần kiểm tra kết quả `remove`. Nếu xóa một phần tử chưa có, `remove` trả `false`. Sau đó `add` có thể tạo một thành viên mới, làm tăng kích thước. Ví dụ, từ `[draft, done]`, thực hiện `remove("archive")` rồi `add("archive")` sẽ cho `[draft, done, archive]`. Đây không còn là “chỉ chuyển phần tử đang có”.

Nếu gọi `clear`, mọi thành viên đều bị loại khỏi tập. Những lần `add` sau đó thiết lập thứ tự mới theo dữ liệu được đưa vào, không phục hồi thứ tự trước `clear`.

Trong yêu cầu nghiệp vụ, hãy chọn rõ một trong hai ý:

- “Đã có thì giữ nguyên vị trí”: chỉ cần `add`.
- “Nếu đang có thì đưa về cuối”: cần thao tác định vị phù hợp với phiên bản Java, hoặc một quy trình xóa/thêm được thiết kế rõ.

## 6. addAll không đưa các phần tử cũ về cuối

Giả sử trạng thái hiện tại là:

~~~text
[draft, review, done]
~~~

Lô tiếp theo có thứ tự:

~~~text
[review, publish, draft, archive]
~~~

Trong lô này, `review` và `draft` đã có. Chúng giữ vị trí cũ. `publish` và `archive` chưa có nên được nối thêm theo thứ tự chúng được gặp trong lô:

~~~text
[draft, review, done, publish, archive]
~~~

`addAll` trả `true` vì có ít nhất một thành viên mới. Giá trị đó không cho biết “mọi phần tử trong lô đều mới” hay “tập đã được sắp lại giống lô đầu vào”. Cách triển khai `addAll` được kế thừa từ `AbstractCollection` duyệt nguồn và gọi `add` cho các phần tử. [Java 17: AbstractCollection.addAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html#addAll(java.util.Collection)).

Nếu cả lô chỉ gồm những phần tử đã có, tập không nhận thành viên mới và thứ tự vẫn giữ nguyên. Không có cơ chế tự làm mới vị trí cho mỗi lần gặp bản trùng.

Tuy nhiên, phải biết thứ tự của nguồn. `List.of("review", "publish", "draft", "archive")` cho một trình tự rõ ràng. Nếu nguồn là `HashSet`, thứ tự duyệt của nguồn không được cam kết. Sao chép sang `LinkedHashSet` chỉ ghi nhận trình tự mà nguồn cung cấp trong lần duyệt đó; nó không suy ra thứ tự chèn ban đầu đã mất.

Với nguồn có thứ tự rõ, bạn có thể giải thích kết quả bằng việc gạch bỏ các giá trị đã có trong tập đích, rồi nối những giá trị mới vào cuối theo trình tự nguồn. Khi cùng một giá trị mới lặp lại trong lô, chỉ lần thêm mới thành công đầu tiên tạo vị trí.

## 7. Khác tham chiếu vẫn có thể là thêm trùng

Đối với tập dùng băm, việc nhận diện phần tử cần quy tắc `equals` và `hashCode` nhất quán. Nếu hai đối tượng được xem là bằng nhau thì chúng phải có cùng mã băm. Hai đối tượng có cùng mã băm chưa chắc bằng nhau.

Hãy xét vé có `number` và `note`. Giả sử nghiệp vụ xem số vé là định danh: hai vé cùng `number` là cùng một phần tử đối với tập, bất kể `note`. Chương trình đầy đủ phía dưới tự định nghĩa `equals` và `hashCode` của `Ticket` chỉ từ `number`. Đây là lựa chọn tường minh; `record Ticket(int number, String note)` mặc định sẽ so sánh cả hai thành phần nếu không ghi đè.

Ta có hai đối tượng:

~~~text
original    = #10:old
replacement = #10:new
~~~

Hai tham chiếu khác nhau nhưng `original.equals(replacement)` bằng `true`. Khi tập đang có `original` và nhận `add(replacement)`, không có thành viên mới. Trong cách triển khai của `LinkedHashSet`, đối tượng cũ vẫn được giữ; việc gọi `add` không cập nhật trường `note` của nó.

Nếu tập hiện là:

~~~text
[#10:old, #20:other]
~~~

thì thêm `#10:new` không tạo kết quả `[#10:new, #20:other]` và cũng không tạo `[#20:other, #10:new]`. Kết quả vẫn là:

~~~text
[#10:old, #20:other]
~~~

Muốn thay đại diện bằng đối tượng mới qua xóa/thêm, bạn phải chấp nhận cả hệ quả về thứ tự:

~~~text
remove(#10:new) → xóa phần tử tương đương #10:old
add(#10:new)    → thêm đối tượng mới ở cuối
kết quả        → [#20:other, #10:new]
~~~

Vì `remove` cũng tìm theo quy tắc bằng nhau, đối tượng dùng để tìm không nhất thiết là chính tham chiếu đang được lưu.

Nếu yêu cầu là “giữ vị trí ban đầu nhưng luôn cập nhật thông tin theo mã vé”, đừng kỳ vọng `Set.add` làm việc thay dữ liệu. Một `LinkedHashMap<Integer, Ticket>` với số vé làm khóa có thể diễn đạt yêu cầu cập nhật giá trị rõ hơn: ở chế độ thứ tự chèn, cập nhật giá trị cho khóa đang có không tự chuyển vị trí khóa. Đây là thiết kế khác với xóa rồi thêm một phần tử của tập. [Java 17: LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

Để các suy luận trên đúng, đừng thay đổi những thuộc tính tham gia `equals/hashCode` khi đối tượng còn trong tập. Nếu mã băm hoặc quan hệ bằng nhau đổi trong thời gian lưu, việc tìm/xóa có thể sai với điều bạn tưởng. Bài học dùng thành phần bất biến của `record` và mã vé cố định để tách vấn đề đó khỏi quy tắc thứ tự.

## 8. null cũng có vị trí, nhưng chỉ một thành viên

`LinkedHashSet` cho phép `null`. Từ trạng thái `[start, null, end]`:

- `add(null)` trả `false` và giữ `[start, null, end]`.
- Xóa `null` rồi thêm `null` lại cho `[start, end, null]`.

Không có quy tắc riêng “`null` luôn ở đầu” hay “`null` luôn ở cuối”. Vị trí quan sát được đến từ quá trình đưa nó vào tập và các thao tác sau đó.

`null` là giá trị đặc biệt không có phương thức để gọi. Bạn không cần gọi `null.equals(...)`; cách triển khai tập xử lý trường hợp này.

Đừng dùng `List.of("start", null, "end")` để tạo đầu vào cho ví dụ vì `List.of` không cho phép `null`. Chương trình bên dưới thêm từng phần tử để kiểm chứng đúng hành vi của `LinkedHashSet` mà không bị dừng trước bởi lỗi tạo danh sách.

## 9. Chương trình đầy đủ: dự đoán rồi mới chạy

Lưu đoạn sau thành `LinkedHashSetReinsertDemo.java`. Chương trình không phụ thuộc thư viện ngoài JDK. Nó kiểm tra riêng việc thêm trùng, thêm theo lô, xóa/thêm, đại diện của đối tượng tương đương, `null`, so sánh thứ tự và bộ duyệt.

Trước khi chạy, hãy dự đoán ba điều:

1. `review` đứng ở đâu sau `add("review")` và sau xóa/thêm?
2. Vé số 10 giữ `note` nào khi thêm đối tượng tương đương?
3. Hai tập `[A, B]` và `[B, A]` có bằng nhau theo `Set.equals` không?

~~~java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedHashSet;
import java.util.List;

public class LinkedHashSetReinsertDemo {
    record Ticket(int number, String note) {
        @Override
        public boolean equals(Object other) {
            return other instanceof Ticket ticket
                    && number == ticket.number;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(number);
        }

        @Override
        public String toString() {
            return "#" + number + ":" + note;
        }
    }

    static <E> boolean moveExistingToEnd(LinkedHashSet<E> set, E element) {
        if (!set.remove(element)) {
            return false;
        }
        set.add(element);
        return true;
    }

    public static void main(String[] args) {
        LinkedHashSet<String> steps =
                new LinkedHashSet<>(List.of("draft", "review", "done"));

        System.out.println("initial=" + steps);
        System.out.println("add(review)=" + steps.add("review"));
        System.out.println("after duplicate=" + steps);
        System.out.println("contains(draft)=" + steps.contains("draft"));
        System.out.println("after contains=" + steps);
        System.out.println("addAll="
                + steps.addAll(List.of("review", "publish", "draft", "archive")));
        System.out.println("after addAll=" + steps);
        System.out.println("remove(review)=" + steps.remove("review"));
        System.out.println("add(review) after remove=" + steps.add("review"));
        System.out.println("after reinsert=" + steps);
        System.out.println("remove(missing)=" + steps.remove("missing"));
        System.out.println("after missing remove=" + steps);
        System.out.println("move(draft)=" + moveExistingToEnd(steps, "draft"));
        System.out.println("after move=" + steps);
        System.out.println("move(missing)=" + moveExistingToEnd(steps, "missing"));
        System.out.println("after missing move=" + steps);

        Ticket original = new Ticket(10, "old");
        Ticket replacement = new Ticket(10, "new");
        LinkedHashSet<Ticket> tickets = new LinkedHashSet<>();
        tickets.add(original);
        tickets.add(new Ticket(20, "other"));
        System.out.println("tickets initial=" + tickets);
        System.out.println("equal ticket=" + original.equals(replacement));
        System.out.println("add equal ticket=" + tickets.add(replacement));
        System.out.println("tickets after duplicate=" + tickets);
        System.out.println("original retained=" + (tickets.iterator().next() == original));
        System.out.println("remove equal ticket=" + tickets.remove(replacement));
        System.out.println("add replacement=" + tickets.add(replacement));
        System.out.println("tickets after replace=" + tickets);
        System.out.println("replacement retained="
                + (new ArrayList<>(tickets).get(1) == replacement));

        LinkedHashSet<String> withNull = new LinkedHashSet<>();
        withNull.add("start");
        withNull.add(null);
        withNull.add("end");
        System.out.println("null initial=" + withNull);
        System.out.println("add(null)=" + withNull.add(null));
        System.out.println("null after duplicate=" + withNull);
        withNull.remove(null);
        withNull.add(null);
        System.out.println("null after reinsert=" + withNull);

        LinkedHashSet<String> forward =
                new LinkedHashSet<>(List.of("A", "B"));
        LinkedHashSet<String> backward =
                new LinkedHashSet<>(List.of("B", "A"));
        System.out.println("set equality=" + forward.equals(backward));
        System.out.println("iteration order equality="
                + new ArrayList<>(forward).equals(new ArrayList<>(backward)));

        LinkedHashSet<Integer> many = new LinkedHashSet<>(1);
        List<Integer> expected = new ArrayList<>();
        for (int value : new int[] {40, 10, 30}) {
            many.add(value);
            expected.add(value);
        }
        for (int value = 100; value < 200; value++) {
            many.add(value);
            expected.add(value);
        }
        System.out.println("many size=" + many.size());
        System.out.println("many insertion order="
                + new ArrayList<>(many).equals(expected));
        System.out.println("many add(10)=" + many.add(10));
        System.out.println("many order after duplicate="
                + new ArrayList<>(many).equals(expected));

        LinkedHashSet<String> directions =
                new LinkedHashSet<>(List.of("north", "south", "west"));
        Iterator<String> iterator = directions.iterator();
        System.out.println("iterator first=" + iterator.next());
        System.out.println("iterator duplicate=" + directions.add("south"));
        System.out.println("iterator next=" + iterator.next());
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 LinkedHashSetReinsertDemo.java
java LinkedHashSetReinsertDemo
~~~

`--release 17` yêu cầu trình biên dịch kiểm tra mã và API theo Java 17. Dùng JDK 17 trở lên cho các lệnh này. Các lớp `record` có mặt trong phạm vi phiên bản đó.

Kết quả chuẩn:

~~~text
initial=[draft, review, done]
add(review)=false
after duplicate=[draft, review, done]
contains(draft)=true
after contains=[draft, review, done]
addAll=true
after addAll=[draft, review, done, publish, archive]
remove(review)=true
add(review) after remove=true
after reinsert=[draft, done, publish, archive, review]
remove(missing)=false
after missing remove=[draft, done, publish, archive, review]
move(draft)=true
after move=[done, publish, archive, review, draft]
move(missing)=false
after missing move=[done, publish, archive, review, draft]
tickets initial=[#10:old, #20:other]
equal ticket=true
add equal ticket=false
tickets after duplicate=[#10:old, #20:other]
original retained=true
remove equal ticket=true
add replacement=true
tickets after replace=[#20:other, #10:new]
replacement retained=true
null initial=[start, null, end]
add(null)=false
null after duplicate=[start, null, end]
null after reinsert=[start, end, null]
set equality=true
iteration order equality=false
many size=103
many insertion order=true
many add(10)=false
many order after duplicate=true
iterator first=north
iterator duplicate=false
iterator next=south
~~~

## 10. Đọc kết quả theo từng thay đổi trạng thái

### 10.1. Thêm trùng và kiểm tra sự hiện diện

Hai dòng `add(review)=false` và `after duplicate=[draft, review, done]` trả lời hai câu hỏi khác nhau: không có thành viên mới và thứ tự không đổi.

Sau `contains(draft)=true`, `draft` vẫn đứng đầu. Tập đang ghi nhận thứ tự đưa phần tử vào, không ghi thời điểm từng được tra cứu.

### 10.2. Thêm theo lô

`addAll=true` xuất hiện vì `publish` và `archive` mới. `review` không bị kéo ra sau `done`; `draft` không bị kéo ra sau `publish`. Trình tự của các phần tử đã có vẫn được bảo toàn.

Điểm cần quan sát là phần đuôi mới `publish, archive`. Đó là thứ tự các giá trị mới được gặp trong lô `List` đầu vào.

### 10.3. Xóa/thêm và chuyển phần tử đang có

Sau khi xóa rồi thêm `review`, kết quả là `[draft, done, publish, archive, review]`. Số phần tử cuối cùng vẫn là năm nhưng đã xảy ra hai lần thay đổi thành viên.

Hàm `moveExistingToEnd` sau đó chuyển `draft` về cuối. Hàm trả `false` khi tên cần chuyển không có trong tập và không tạo thêm tên ấy. Điều kiện `if (!set.remove(element))` là phần quyết định ngữ nghĩa “chỉ chuyển phần tử đang có”.

Nếu dùng một hàm luôn `remove` rồi `add` không kiểm tra kết quả xóa, giá trị chưa có sẽ được thêm mới. Hai hàm có thể cùng cho kết quả với dữ liệu đã có nhưng khác hành vi với dữ liệu vắng mặt.

### 10.4. Đại diện cũ và đại diện mới

`equal ticket=true` xác nhận hai vé số 10 tương đương theo quy tắc đã chọn. `add equal ticket=false` xác nhận không tăng thành viên.

`original retained=true` dùng `==` có chủ đích: nó kiểm tra tham chiếu thực tế của đại diện đang lưu, không chỉ tính bằng nhau theo nghiệp vụ. Kết quả `#10:old` cho biết `add` trùng không cập nhật nội dung từ đối tượng `replacement`.

Sau xóa/thêm, vé số 20 lên trước và `#10:new` xuống cuối. `replacement retained=true` xác nhận đối tượng mới đã trở thành đại diện. Muốn kết luận về việc thay đại diện, chỉ kiểm tra `contains(replacement)` là chưa đủ, vì kết quả đó cũng có thể là `true` khi đại diện cũ còn trong tập.

### 10.5. So sánh thành viên và so sánh trình tự

`set equality=true` trong khi `iteration order equality=false` là hoàn toàn nhất quán. Hai tập chứa cùng `A` và `B`, nhưng có trình tự duyệt khác.

Chuyển từng tập sang `ArrayList` tạo hai ảnh chụp thứ tự để so sánh bằng `List.equals`. Bước này giúp kiểm tra điều mà `Set.equals` không kiểm tra. Không dùng việc hai tập bằng nhau làm bằng chứng rằng chúng sẽ in cùng một chuỗi thứ tự. Hợp đồng `Set.equals` dựa trên thành viên, không dựa trên vị trí. [Java 17: Set.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#equals(java.lang.Object)).

### 10.6. Nhiều lần thêm không làm mất cam kết thứ tự

Phần `many` bắt đầu với dung lượng khởi tạo nhỏ và thêm 103 số khác nhau theo một trình tự được lưu riêng trong `expected`. Chương trình in `many insertion order=true` và vẫn in `true` sau khi thêm trùng số 10.

Phép thử này đối chiếu kết quả duyệt với trình tự thao tác. Nó không đo số lần mở rộng bảng, số ngăn hay bố trí bên trong. Không suy một công thức dung lượng từ số `103`. Điều được kiểm chứng ở đây là nhiều lần thêm vẫn giữ thứ tự theo hợp đồng.

### 10.7. Thêm trùng khi đang dùng iterator

Bộ duyệt `directions` đã lấy `north`. Lời gọi thêm `south` trả `false`, không thêm hoặc xóa thành viên; lần `next` kế tiếp vẫn lấy `south`.

Trường hợp này khác với việc xóa `south` rồi thêm lại giữa lúc bộ duyệt cũ đang hoạt động. Chuỗi xóa/thêm thay đổi cấu trúc dù kích thước cuối cùng có thể bằng kích thước ban đầu. Đừng dùng phép so sánh `size` trước/sau để quyết định bộ duyệt cũ có còn hợp lệ hay không.

## 11. Hàm chuyển về cuối cần hợp đồng riêng

Hàm trong chương trình:

~~~java
static <E> boolean moveExistingToEnd(LinkedHashSet<E> set, E element) {
    if (!set.remove(element)) {
        return false;
    }
    set.add(element);
    return true;
}
~~~

Đây là đoạn trích từ chương trình hoàn chỉnh, không phải API có sẵn trong JDK. Nó có ba đặc điểm cần đọc đúng.

Thứ nhất, giá trị trả về `true` biểu thị phần tử đã tồn tại và quy trình xóa/thêm được thực hiện. Nó không khẳng định vị trí cuối cùng khác vị trí trước đó. Nếu phần tử vốn đã cuối, hàm vẫn xóa rồi thêm và trả `true`.

Thứ hai, hàm đưa chính đối tượng `element` truyền vào làm đại diện khi thêm lại. Với `String` bất biến và cùng giá trị, khác biệt tham chiếu thường không đáng chú ý. Với `Ticket` mà `note` không tham gia phép bằng nhau, hành vi này có thể thay dữ liệu đang lưu. Tên hàm chỉ nói về vị trí; người thiết kế vẫn phải quyết định có cho phép thay đại diện hay cần giữ đối tượng cũ.

Thứ ba, hai thao tác không phải một hành động nguyên tử. Một luồng khác có thể xen vào nếu dữ liệu được chia sẻ mà không phối hợp đồng bộ. Nếu nghiệp vụ cần “kiểm tra rồi chuyển” như một bước không thể bị xen ngang, phải bảo vệ cả quy trình cùng các truy cập liên quan. Chỉ thấy phương thức ngắn hoặc kết quả cuối có cùng số phần tử không tạo ra tính an toàn khi nhiều luồng cùng dùng.

Trong ví dụ, dữ liệu ổn định, quy tắc bằng nhau hợp lệ và chỉ một luồng thao tác. Hàm giúp quan sát cách tạo vị trí mới bằng Java 17. Với đối tượng phức tạp hoặc yêu cầu cạnh tranh giữa nhiều luồng, cần xác định hợp đồng dữ liệu trước khi tái sử dụng nguyên xi.

## 12. Giữ thứ tự chèn không phải tự động theo dõi lần dùng gần nhất

Một hàng đợi “vừa dùng gần đây” thường cần chuyển phần tử lên vị trí ưu tiên sau mỗi lần sử dụng. Ví dụ, người dùng vừa mở lại tài liệu `draft` thì tài liệu đó phải trở thành mục mới dùng nhất.

`LinkedHashSet.add("draft")` trên một tập đã có `draft` không làm việc đó. Gọi `contains("draft")` cũng không làm việc đó. Nếu dùng những lời gọi này làm cách “chạm để làm mới”, giao diện có thể giữ thứ tự cũ dù sự kiện mới đã đến.

Phân biệt các yêu cầu:

| Yêu cầu | Ý nghĩa của lần gặp lại |
| --- | --- |
| Giữ vị trí ghi nhận ban đầu khi phần tử còn trong tập | Bỏ qua bản trùng và giữ chỗ cũ |
| Sắp theo lần xuất hiện mới nhất | Phải cập nhật vị trí khi có sự kiện mới |
| Cập nhật dữ liệu theo định danh, giữ thứ tự định danh | Thay thông tin gắn với định danh, giữ chỗ của khóa |
| Ghi lại mọi sự kiện | Mỗi lần xuất hiện phải được lưu, kể cả giá trị lặp |

Bốn yêu cầu không thể suy ra chỉ từ câu “cần giữ thứ tự”. Cần làm rõ thứ tự theo sự kiện nào và có giữ mọi lần xuất hiện hay không.

`LinkedHashMap` có chế độ thứ tự truy cập khi dùng hàm khởi tạo với `accessOrder=true`; những thao tác truy cập được quy định, chẳng hạn `get`, có thể ảnh hưởng vị trí. Khả năng này không trở thành hành vi của `LinkedHashSet.add` chỉ vì hai lớp có liên hệ trong cách triển khai. Chế độ thứ tự truy cập cũng không tự cung cấp toàn bộ chính sách dung lượng, hết hạn hay đồng bộ cho một bộ nhớ đệm. [Java 17: LinkedHashMap, chế độ thứ tự truy cập](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

Nếu cần ghi lịch sử mọi lần xảy ra, một tập loại trùng đã làm mất thông tin về số lần xuất hiện. Khi đó phải chọn mô hình lưu sự kiện phù hợp, thay vì cố suy lại lịch sử từ `LinkedHashSet` cuối cùng.

## 13. Lưu ý phiên bản: add khác addFirst và addLast

Quy tắc “thêm phần tử đã có không đổi vị trí” trong bài áp dụng cho `add` thông thường. Từ Java 21, `LinkedHashSet` triển khai `SequencedSet` và có các phương thức định vị tường minh như `addFirst` và `addLast`.

Theo API Java 21, khi phần tử đã tồn tại, `addFirst` có thể chuyển nó về đầu và `addLast` có thể chuyển nó về cuối. Nếu phần tử chưa có, chúng thêm nó ở vị trí tương ứng. Hai phương thức trả `void` và không cùng chữ ký hoặc ý nghĩa với `boolean add(E)`. [Java 21: LinkedHashSet.addFirst và addLast](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashSet.html#addFirst(E)).

Bởi vậy, hãy đọc chính xác tên phương thức trong mã. Một nhận xét đúng với `set.add(e)` không chứng minh kết quả của `set.addLast(e)`. Ngược lại, thấy `addLast` chuyển vị trí trong mã Java 21 không có nghĩa rằng `add` cũng đổi hành vi.

Chương trình của bài dùng xóa/thêm để giữ khả năng biên dịch theo Java 17. Các phương thức mới không có trong bộ API mà `--release 17` cho phép. Nếu dự án đã chọn Java 21 trở lên và cần định vị tường minh, có thể cân nhắc API đó với đúng hợp đồng của nó.

Cũng không tự đồng nhất “chuyển vị trí phần tử đã có” với “xóa rồi thêm đối tượng tương đương khác”. Ví dụ vé số 10 cho thấy chuỗi xóa/thêm của bài có thêm hệ quả về đại diện được lưu. Khi yêu cầu cập nhật cả dữ liệu lẫn vị trí, hãy kiểm tra từng hệ quả riêng.

## 14. Chi phí và giới hạn ảnh hưởng trực tiếp đến cách sử dụng

Với hàm băm phân tán tốt, các thao tác cơ bản `add`, `contains` và `remove` có hiệu năng thời gian hằng theo kỳ vọng sử dụng thông thường. Điều đó không có nghĩa mọi kiểu đối tượng, mọi phân bố mã băm đều cho cùng chi phí. Thời gian tính `hashCode` và `equals` của phần tử cũng góp vào chi phí thực tế.

`LinkedHashSet` phải duy trì liên kết để giữ thứ tự. Khi duyệt toàn bộ, thời gian tỷ lệ với số phần tử đang có, không phải phải đi tìm vị trí bằng cách quét danh sách từ đầu mỗi lần thêm. Đổi lại, có thông tin liên kết cần lưu và cập nhật. Không dùng suy luận “có liên kết thì luôn nhanh hơn” để chọn cấu trúc.

Chuỗi xóa/thêm thực hiện hai thao tác thay đổi thành viên và làm mất vị trí cũ. Nếu yêu cầu chỉ là bỏ qua bản trùng, gọi `add` trực tiếp vừa thể hiện đúng ý vừa tránh những hệ quả không cần thiết.

Khi đang duyệt, không tự xóa/thêm qua tập rồi tiếp tục dùng bộ duyệt cũ. Bộ duyệt của `LinkedHashSet` có cơ chế phát hiện thay đổi để báo lỗi sớm; `ConcurrentModificationException` hỗ trợ phát hiện lỗi và không phải cơ chế đồng bộ được bảo đảm. Dù không thấy ngoại lệ trong một thử nghiệm, bạn vẫn không được dựa vào điều đó để chứng minh mã sửa tập trong lúc duyệt là đúng. [Java 17: HashSet, bộ duyệt và giới hạn fail-fast](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html).

Nếu cần đổi thứ tự nhiều phần tử dựa trên kết quả duyệt, cách rõ ràng hơn là ghi nhận kế hoạch vào một cấu trúc riêng, kết thúc lượt duyệt, rồi áp dụng thay đổi. Cần quy định rõ kết quả khi nhiều phần tử cùng được chuyển để thứ tự cuối không phụ thuộc một vòng lặp sửa dữ liệu khó theo dõi.

## 15. Những lỗi suy luận dễ gặp

| Nhận định | Cách kiểm tra đúng |
| --- | --- |
| “Gọi `add` là đưa phần tử về cuối” | Kiểm tra phần tử đã có hay chưa; `add` trùng giữ vị trí |
| “`add` trả `false` nên phần tử không có trong tập” | `false` biểu thị không thêm thành viên mới; phần tử có thể đã tồn tại |
| “Đối tượng vừa `new` chắc chắn là phần tử mới” | So sánh theo `equals/hashCode`, không chỉ tham chiếu |
| “Thêm đối tượng cùng mã sẽ cập nhật dữ liệu cũ” | Kiểm tra đối tượng đại diện; `Set.add` không phải phép cập nhật bản ghi |
| “Xóa rồi thêm chỉ đổi vị trí” | Nó còn có thể thay đại diện và làm bộ duyệt cũ mất hiệu lực |
| “Số phần tử không đổi nên không có thay đổi cấu trúc” | Xóa một rồi thêm một vẫn là hai thay đổi |
| “`addAll` sắp tập theo lô mới nhất” | Các thành viên cũ giữ chỗ; chỉ thành viên mới được nối thêm |
| “Hai tập bằng nhau thì thứ tự giống nhau” | `Set.equals` không xét vị trí; so sánh ảnh chụp `List` nếu thứ tự là yêu cầu |
| “Giữ thứ tự nghĩa là đã sắp xếp tăng dần” | Thứ tự chèn phụ thuộc thao tác; không tự thành thứ tự theo giá trị |
| “Bản sao từ `HashSet` khôi phục lịch sử chèn” | Bản sao chỉ nhận thứ tự duyệt mà nguồn cung cấp |
| “Có LinkedHashMap bên trong thì đây là tập theo lần truy cập” | Đọc hợp đồng `LinkedHashSet`; `add` và `contains` không làm mới vị trí |
| “Mọi phương thức thêm đều giống `add`” | Tách API định vị `addFirst/addLast` của Java 21 khỏi `add` |

Một thói quen hữu ích là ghi trạng thái trước, thao tác, giá trị trả về và trạng thái sau trên bốn dòng. Cách đó buộc bạn phân biệt “không có thành viên mới” với “không có phần tử”, cũng như “cùng kích thước” với “cùng lịch sử thay đổi”.

## 16. Thực hành có lời giải

### Bài 1: dự đoán add trùng

Trạng thái ban đầu là `[red, green, blue]`. Thực hiện `add("green")`, sau đó `add("yellow")`. Hai giá trị trả về và thứ tự cuối là gì?

**Lời giải:** Lần đầu trả `false` vì `green` đã có và giữ vị trí giữa. Lần sau trả `true` và nối `yellow` vào cuối. Kết quả là `[red, green, blue, yellow]`. Không có bước nào chuyển `green`.

### Bài 2: phân biệt thêm trùng với tái gia nhập

Từ `[red, green, blue]`, thực hiện `remove("red")`, `add("green")`, `add("red")`.

**Lời giải:** Xóa `red` thành công cho `[green, blue]`. Thêm `green` trùng trả `false` và giữ nguyên. Thêm `red` sau khi đã xóa trả `true`, cho `[green, blue, red]`. Tập không lưu chỗ đầu cũ của `red`.

### Bài 3: lô có cả phần tử cũ lẫn mới

Tập ban đầu là `[A, B]`. Nguồn có thứ tự `[B, C, A, D, C]`. Gọi `addAll` thì kết quả nào?

**Lời giải:** `B` và `A` đã có nên không đổi chỗ. `C` lần đầu và `D` là mới. `C` lần cuối lại trùng. Kết quả là `[A, B, C, D]` và `addAll` trả `true`. Đây không phải thứ tự của lần xuất hiện cuối.

### Bài 4: thay thông tin của phần tử

Dùng quy tắc `Ticket` trong chương trình. Tập là `[#10:old, #20:other]`. Thêm `new Ticket(10, "new")` rồi kiểm tra `contains` bằng vé mới. Có thể kết luận thông tin `new` đã được lưu không?

**Lời giải:** Không. `contains` tìm theo số vé nên có thể trả `true` dù đại diện vẫn là `#10:old`. Phải kiểm tra đại diện hoặc chọn cấu trúc hỗ trợ cập nhật thông tin theo khóa. `add` trùng không có nghĩa cập nhật thành công.

### Bài 5: viết phép kiểm tra đúng cho thứ tự

Bạn tạo hai `LinkedHashSet` có cùng thành viên nhưng chèn theo hai trình tự khác nhau. Kiểm tra `first.equals(second)` trả `true`. Làm sao phát hiện khác thứ tự?

**Lời giải:** Trong một thời điểm dữ liệu ổn định, tạo `new ArrayList<>(first)` và `new ArrayList<>(second)`, rồi so sánh hai danh sách. `List.equals` xét trình tự. Phép kiểm tra này bổ sung yêu cầu thứ tự mà phép bằng nhau của tập không thể hiện.

### Bài 6: hàm chuyển và phần tử chưa có

Với `[A, B]`, gọi `moveExistingToEnd(set, "C")` trong chương trình. Sau đó gọi `moveExistingToEnd(set, "A")`. Tập và giá trị trả về là gì?

**Lời giải:** Lần đầu trả `false` và vẫn `[A, B]` vì hàm không tự thêm giá trị chưa có. Lần sau trả `true` và cho `[B, A]`. Nếu hàm luôn xóa rồi thêm không kiểm tra kết quả, lần đầu đã tạo `C` và mang ngữ nghĩa khác.

### Bài 7: chọn lời gọi theo phiên bản Java

Bạn cần đưa một phần tử đang có về cuối. Mã phải biên dịch với `--release 17`. Có thể thay `add` bằng `addLast` không?

**Lời giải:** Không trong bộ API Java 17. Bạn cần một quy trình tương thích phiên bản, chẳng hạn xóa/thêm với hợp đồng rõ về phần tử vắng mặt, đại diện và việc đồng bộ. Nếu chuyển dự án sang Java 21 trở lên, có thể xem xét `addLast` theo hợp đồng của phương thức đó. Đổi tên lời gọi không làm API mới xuất hiện trong Java 17.

## 17. Tự kiểm tra khi áp dụng vào mã thật

Trước khi dùng `LinkedHashSet` cho một luồng dữ liệu, hãy trả lời được các câu sau:

- Quy tắc xác định trùng là gì và `equals/hashCode` có phản ánh nó không?
- Bạn cần giữ chỗ của lần thêm thành công đầu tiên đang còn hiệu lực hay cần ưu tiên lần xuất hiện mới nhất?
- Giá trị đến sau chỉ là bản trùng hay mang thông tin cần cập nhật?
- Khi xóa rồi thêm đối tượng tương đương, có chấp nhận thay đại diện được lưu không?
- Nguồn của `addAll` có thứ tự được cam kết không?
- Phép kiểm tra đang so sánh thành viên hay thực sự so sánh trình tự duyệt?
- Có bộ duyệt cũ hoặc luồng khác đang dùng tập trong lúc bạn thay đổi không?
- Phiên bản Java của dự án có đúng với API định vị mà mã gọi không?

Điểm phải giữ chính xác trong mọi ví dụ là thời điểm xét sự hiện diện. Nếu phần tử đã có ngay trước `add`, lời gọi đó không đưa nó đến cuối. Nếu nó đã bị xóa, lần `add` tiếp theo là một lần gia nhập mới và tạo vị trí mới ở cuối trong các thao tác thông thường của bài.
