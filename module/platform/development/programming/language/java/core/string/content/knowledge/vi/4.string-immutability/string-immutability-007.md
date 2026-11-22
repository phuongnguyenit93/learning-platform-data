# Lợi ích của tính bất biến khi dùng String làm khóa, chia sẻ dữ liệu và xử lý đồng thời

**String là một kiểu tham chiếu nhưng nội dung của một đối tượng String không thể thay đổi sau khi đối tượng được tạo.** Đây là tính *bất biến* (*immutability*). Những phương thức như concat(), replace(), substring(), toUpperCase() hay trim() không sửa đối tượng hiện tại; chúng trả về String kết quả, có thể là đối tượng mới hoặc chính đối tượng ban đầu nếu không cần thay đổi nội dung.

Tính bất biến tạo ra ba lợi ích nổi bật trong ứng dụng Java:

1. **Làm khóa ổn định** trong HashMap, HashSet, cache và các cấu trúc dựa trên equals()/hashCode().
2. **Chia sẻ dữ liệu dễ dự đoán** giữa phương thức, thành phần và luồng: nơi nhận không thể sửa nội dung String mà nơi gửi đang nắm giữ.
3. **Đọc và xử lý đồng thời thuận lợi hơn**: nhiều luồng có thể dùng cùng một giá trị String mà không phải khóa để bảo vệ chính nội dung của giá trị đó.

Lợi ích thứ ba có **giới hạn quan trọng**: String bất biến không làm cho biến tham chiếu, Map, List hoặc toàn bộ đối tượng chứa String trở thành an toàn khi nhiều luồng cùng thay đổi.

## 1. Tính ổn định nằm ở chính giá trị văn bản

Hai biến có thể cùng giữ tham chiếu tới một `String`; các thao tác biến đổi trả về giá trị để sử dụng mà không thay đổi nội dung chuỗi đã tạo. Nhờ vậy, nơi đang giữ một khóa hoặc bản báo cáo không bất ngờ thấy ký tự bị sửa từ một nơi khác. Biến hoặc trường chứa tham chiếu vẫn có thể được gán lại, vì thế lợi ích này có phạm vi là **giá trị String**, không bao gồm toàn bộ trạng thái mutable xung quanh nó.

## 2. Lợi ích khi dùng String làm khóa của HashMap và HashSet

Một khóa của HashMap cần có hành vi equals() và hashCode() ổn định khi nằm trong Map. HashMap sử dụng hashCode() để định vị vùng lưu trữ và dùng equals() khi cần xác định các khóa có nội dung tương đương. HashSet dựa trên nguyên tắc tương ứng để lưu các phần tử duy nhất.

Đối với String:

- equals() so sánh **nội dung**, không chỉ so sánh hai tham chiếu.
- Hai String có nội dung bằng nhau có cùng giá trị hashCode().
- Nội dung String không đổi, nên hashCode() và kết quả so sánh nội dung của một đối tượng không thay đổi theo thời gian.
- Có thể tạo một String khác nhưng nội dung bằng nhau để tra cứu khóa đã lưu mà không cần giữ đúng cùng một instance.

Ví dụ minh họa:

~~~java
import java.util.HashMap;
import java.util.Map;

public class StringKeyDemo {
    public static void main(String[] args) {
        Map<String, Integer> prices = new HashMap<>();
        String savedKey = "item:42";
        prices.put(savedKey, 150);

        String lookupKey = new StringBuilder("item:")
                .append(42)
                .toString();

        System.out.println(savedKey.equals(lookupKey));
        System.out.println(savedKey.hashCode() == lookupKey.hashCode());
        System.out.println(prices.get(lookupKey));

        String updatedKey = savedKey.replace("42", "43");
        System.out.println(savedKey);
        System.out.println(updatedKey);
        System.out.println(prices.get(savedKey));
        System.out.println(prices.get(updatedKey));
    }
}
~~~

Lưu thành **StringKeyDemo.java**, rồi chạy trên JDK 17+:

~~~bash
javac StringKeyDemo.java
java StringKeyDemo
~~~

Kết quả:

~~~text
true
true
150
item:42
item:43
150
null
~~~

**Giải thích:** lookupKey có nội dung bằng savedKey nên Map tìm được giá trị 150. replace() tạo giá trị updatedKey khác; savedKey vẫn là "item:42", vì vậy khóa đã đặt trong Map giữ nguyên. Không có bản ghi "item:43" nên lần tra cứu cuối trả về null.

### Nếu khóa có thể bị sửa thì sao?

Giả sử một lớp tự định nghĩa dùng trường id mutable trong equals() và hashCode(); đưa instance vào HashMap rồi sửa id sau đó có thể khiến việc tra cứu bằng khóa ấy hoặc một khóa tương đương không tìm được bản ghi như mong đợi. Nguyên nhân là giá trị băm tại lúc đưa khóa vào cấu trúc có thể khác với giá trị băm sau khi sửa.

String tránh được riêng nguy cơ **nội dung khóa bị sửa sau khi chèn**. Nhưng không có nghĩa tất cả khóa hợp lệ đều phải là String: một đối tượng bất biến khác với equals()/hashCode() nhất quán cũng có thể là khóa tốt.

**Không nhầm StringBuilder hay StringBuffer với String khi dùng làm khóa:** hai lớp bộ đệm không định nghĩa equals()/hashCode() để so sánh nội dung giống String. Việc cùng in ra một chuỗi không có nghĩa hai đối tượng builder/buffer là hai khóa tương đương. Nếu dữ liệu dùng để xây khóa đang ở StringBuilder, hãy hoàn thiện rồi gọi toString() để tạo khóa String.

### Những điều String không tự giải quyết khi làm khóa

- **Hash collision vẫn có thể xảy ra:** hai String khác nội dung đôi khi có cùng hashCode(); vì vậy phải dùng equals(), không được lấy riêng hashCode() làm chứng minh hai chuỗi bằng nhau.
- **Khóa phân biệt chữ hoa/chữ thường:** "USER:42" không bằng "user:42" theo String.equals(). Nếu hệ thống muốn bỏ qua chữ hoa/chữ thường, hãy chuẩn hóa theo quy tắc nghiệp vụ trước khi lưu và tra cứu; với mã định danh không phụ thuộc ngôn ngữ có thể dùng toLowerCase(Locale.ROOT).
- **Unicode có nhiều cách biểu diễn:** một số văn bản trông giống nhau vẫn khác dãy đơn vị mã; nếu yêu cầu chuẩn hóa Unicode, cần quy định cách chuẩn hóa nhất quán (chẳng hạn Normalizer) ở cả lúc ghi và đọc.
- **HashMap không tự thread-safe:** khóa String ổn định không cho phép nhiều luồng sửa chung một HashMap mà bỏ qua đồng bộ hóa. Với truy cập cập nhật đồng thời, dùng cơ chế phù hợp như ConcurrentHashMap, khóa hoặc quy tắc chỉ-đọc sau khi xây dựng.

## 3. Lợi ích khi chia sẻ dữ liệu giữa phương thức và thành phần

Một String có thể được chuyển qua tham số, trả về từ hàm, lưu vào đối tượng hoặc truyền sang một thành phần khác mà không lo thành phần nhận chỉnh sửa **nội dung của chính đối tượng String**. Vì vậy việc suy luận về một giá trị đã được tạo đơn giản hơn: những thao tác thay đổi văn bản sẽ tạo ra giá trị mới, không làm âm thầm biến đổi dữ liệu đang dùng ở nơi khác.

Ví dụ sau không thay đổi giá trị của caller:

~~~java
public class ShareStringDemo {
    static String addSuffix(String input) {
        return input.concat("-done");
    }

    public static void main(String[] args) {
        String original = "task";
        String next = addSuffix(original);

        System.out.println(original); // task
        System.out.println(next);     // task-done
    }
}
~~~

Lưu thành **ShareStringDemo.java**, chạy bằng javac ShareStringDemo.java và java ShareStringDemo. Hai dòng in ra lần lượt là task và task-done. Việc hàm nhận tham chiếu tới String không làm hàm có khả năng sửa giá trị gốc.

### Tạo một bản chụp nội dung từ bộ đệm mutable

Một chương trình có thể dựng chuỗi bằng StringBuilder rồi công bố kết quả String cho nơi khác. Sau khi xuất kết quả, những thay đổi sau đó ở builder không ảnh hưởng tới String đã tạo:

~~~java
StringBuilder draft = new StringBuilder("version 1");
String published = draft.toString();

draft.replace(0, draft.length(), "version 2");

System.out.println(published); // version 1
System.out.println(draft);     // version 2
~~~

Cách làm phổ biến là **xây dựng dữ liệu cục bộ bằng StringBuilder, chuyển thành String khi hoàn tất, sau đó chia sẻ String**. Đối với dữ liệu văn bản lớn, vẫn cần lưu ý chi phí bộ nhớ và sao chép; tính bất biến đem lại sự rõ ràng về trạng thái chứ không bảo đảm mọi cách dựng chuỗi đều nhanh nhất.

### Ranh giới của tính bất biến

Một lớp có trường String không nhất thiết là immutable nếu đối tượng đó có setter hoặc các trường mutable khác. Ví dụ:

~~~java
class Config {
    String name;

    void changeName(String next) {
        name = next;
    }
}
~~~

String mà name tham chiếu không thể bị sửa nội dung; tuy nhiên trường name của đối tượng Config vẫn bị thay thế. Nếu Config được chia sẻ giữa nhiều luồng và name bị cập nhật, phải xử lý quy tắc truy cập đồng thời tới **trường name**.

Tương tự, List<String> hay Map<String, String> vẫn là collection có thể thay đổi nếu chọn implementation mutable. Tính bất biến của phần tử/khóa/giá trị không tự bảo vệ thao tác thêm, xóa, thay thế trong collection.

## 4. Lợi ích khi xử lý đồng thời

Hãy phân biệt hai loại trạng thái:

- **Nội dung của String:** không có thao tác nào chỉnh sửa nội dung đối tượng đã tạo. Nhiều luồng có thể đọc và sử dụng cùng String mà không phải khóa chỉ để ngăn nội dung bị thay đổi.
- **Tham chiếu và các cấu trúc chứa String:** vẫn có thể bị cập nhật. Các thao tác trên trạng thái chia sẻ như thay thế trường, thêm phần tử vào List/Map hoặc kiểm tra-rồi-cập-nhật cần cơ chế đồng thời phù hợp.

### Ví dụ nhiều luồng cùng đọc một String

Chương trình sau cho hai luồng đọc cùng một giá trị String và tạo **kết quả riêng**. Không luồng nào có thể làm thay đổi nội dung shared.

~~~java
import java.util.Locale;

public class SharedStringThreadsDemo {
    public static void main(String[] args) throws InterruptedException {
        String shared = "Java";
        String[] outputs = new String[2];

        Thread upper = new Thread(
                () -> outputs[0] = shared.toUpperCase(Locale.ROOT));
        Thread suffix = new Thread(
                () -> outputs[1] = shared.concat(" 17"));

        upper.start();
        suffix.start();

        upper.join();
        suffix.join();

        System.out.println("shared=" + shared);
        System.out.println("upper=" + outputs[0]);
        System.out.println("suffix=" + outputs[1]);
    }
}
~~~

Lưu thành **SharedStringThreadsDemo.java**, chạy:

~~~bash
javac SharedStringThreadsDemo.java
java SharedStringThreadsDemo
~~~

Kết quả:

~~~text
shared=Java
upper=JAVA
suffix=Java 17
~~~

**Vì sao đúng?** shared được giữ nguyên; hai phương thức tạo ra kết quả String riêng. Mỗi luồng ghi vào phần tử khác nhau của mảng outputs, không tranh chấp cùng một ô. main gọi join() trước khi đọc kết quả, nên có quan hệ *happens-before* từ các thao tác trong luồng hoàn tất tới thao tác sau join() ở main. Ví dụ không chứng minh rằng mọi truy cập tới mọi mảng đều thread-safe: thiết kế này đúng vì các luồng ghi phần tử riêng và main chờ hoàn tất.

Không cần dùng synchronized để bảo vệ **nội dung shared**, nhưng vẫn cần cơ chế phối hợp khi có trạng thái khác được sửa đồng thời. Đó là lợi ích trực tiếp của dữ liệu bất biến: phạm vi phải bảo vệ bằng khóa giảm xuống.

### Giới hạn khi nhiều luồng cập nhật trạng thái

Ví dụ trên an toàn vì mỗi luồng ghi một phần tử kết quả riêng, rồi `main` gọi `join()` trước khi đọc. Đây là cách phối hợp luồng rõ ràng; nội dung `String` bất biến chỉ giúp các luồng không thể sửa cùng văn bản `shared`.

Nếu các luồng cùng thay đổi một **trường tham chiếu** kiểu `String` hoặc cùng ghi `Map`, `List`, vẫn phải chọn cơ chế công bố, đồng bộ và cập nhật phù hợp. `volatile String` có thể bảo đảm visibility cho trường, nhưng không làm phép `status = status + suffix` trở thành nguyên tử. Khi cần giữ cả hai cập nhật, xem xét `synchronized`, `AtomicReference.updateAndGet` hoặc API concurrent collection tương ứng. Bài về ranh giới an toàn đa luồng trong chương giải thích bằng ví dụ lost update và `happens-before`.

## 5. Bài tập tình huống: khóa cache và dữ liệu công bố

Giả sử ứng dụng tạo nhãn trạng thái cho nhiều công việc:

1. Mỗi tác vụ nhận một mã công việc dưới dạng String, ví dụ "job:17".
2. Map lưu kết quả theo mã công việc; các lần truy cập dùng String có nội dung bằng nhau để xác định cùng một khóa.
3. Nội dung báo cáo được xây dựng qua nhiều lần append trên StringBuilder **riêng** của tác vụ.
4. Khi xong, tác vụ gọi toString() và chuyển String kết quả sang bước tổng hợp.
5. Nếu nhiều luồng cần cùng cập nhật bộ Map, sử dụng một cơ chế đồng thời như ConcurrentHashMap hoặc khóa phù hợp; nếu Map chỉ được xây dựng trong một luồng rồi công bố để đọc, cần bảo đảm việc công bố được đồng bộ đúng cách.

Ưu điểm của cách thiết kế này là người đọc Map không phải lo một mã khóa String bỗng thay đổi nội dung. Người đọc kết quả cũng không thấy String báo cáo đã công bố bị thay đổi theo builder nội bộ của tác vụ. Các vấn đề còn phải giải quyết nằm ở **quyền sở hữu và đồng bộ hóa bộ Map**, không phải ở nội dung String.

Nếu nghiệp vụ yêu cầu khóa so sánh không phân biệt hoa/thường hoặc có bước chuẩn hóa, hãy biến đổi dữ liệu **trước khi đặt vào Map** và áp dụng chính quy tắc đó cho mọi lần tra cứu. Ví dụ nếu chọn lowercase cho mã định danh máy, hãy dùng một cách chuẩn hóa nhất quán như id.toLowerCase(Locale.ROOT). Immutable chỉ bảo đảm khóa không đổi **sau khi đã tạo**; nó không tự quyết định hai dạng văn bản nào phải được coi là tương đương.

## 6. Ghi nhớ và tự kiểm tra

**Chuỗi suy luận cần nhớ:**

- **Immutable String → nội dung ổn định → equals()/hashCode() ổn định → thuận lợi làm khóa.**
- **Immutable String → nơi nhận không thể sửa nội dung gốc → thuận lợi chia sẻ giá trị và giảm lỗi do aliasing.**
- **Immutable String → nhiều luồng đọc cùng nội dung mà không cần khóa để chống chỉnh sửa → thuận lợi cho xử lý đồng thời.**
- **Immutable String ≠ dữ liệu chứa nó tự thread-safe:** việc cập nhật tham chiếu, collection hoặc nhiều bước vẫn phải được phối hợp.

Hãy tự trả lời các câu hỏi sau trước khi áp dụng:

1. Nếu gọi name.replace("A", "B") mà không lưu kết quả, biến name có thay đổi không?
2. Vì sao HashMap có thể tra cứu bằng một String khác instance nhưng cùng nội dung với khóa ban đầu?
3. Nếu một luồng cập nhật trường status kiểu String và một luồng khác đọc nó, bất biến của String có đủ bảo đảm thấy cập nhật mới hay không?
4. Nếu hai tác vụ đều xây dựng báo cáo, tại sao mỗi tác vụ nên giữ StringBuilder riêng rồi công bố String thay vì sửa chung một StringBuilder?
5. Một Map<String, Integer> có an toàn khi nhiều luồng cùng put() chỉ vì khóa là String hay không?

**Đáp án ngắn:** (1) Không, replace() trả về giá trị. (2) Vì String.equals() so sánh nội dung và hai giá trị bằng nhau có cùng hashCode(). (3) Không, còn cần quan hệ đồng bộ/công bố phù hợp. (4) Tránh chia sẻ bộ đệm mutable và có kết quả đầu ra ổn định. (5) Không, cấu trúc Map cần cơ chế truy cập đồng thời phù hợp.

**Kết luận:** Tính bất biến của String đem lại khả năng làm khóa ổn định, chia sẻ giá trị không lo bị sửa nội dung, và sử dụng cùng dữ liệu trong nhiều luồng dễ an toàn hơn. Sự an toàn đó áp dụng cho **nội dung String**; các biến và cấu trúc mutable quanh nó vẫn cần thiết kế đồng bộ riêng.
