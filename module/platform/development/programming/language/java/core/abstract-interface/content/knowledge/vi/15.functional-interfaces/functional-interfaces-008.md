# Kiểu tham số, kiểu trả về và checked exception trong hợp đồng hàm

Một **functional interface** (interface hàm) định nghĩa một hợp đồng có thể được hiện thực bằng lambda hoặc method reference. Hợp đồng này cho biết hàm nhận những đối số nào, phải trả về giá trị gì và được phép để những checked exception nào truyền ra ngoài. Khi gán lambda cho một kiểu functional interface, Java dùng kiểu đích để kiểm tra ba phần đó ngay lúc biên dịch.

## 1. Phân biệt chữ ký phương thức và hợp đồng hàm

Một functional interface có đúng một phương thức trừu tượng (SAM — *single abstract method*). Có thể dùng **@FunctionalInterface** để nhờ trình biên dịch kiểm tra điều kiện này. Phương thức SAM là kiểu mô tả (function descriptor) mà lambda hoặc method reference phải đáp ứng.

Trong thuật ngữ của Java Language Specification, chữ ký phương thức chủ yếu dựa trên tên, tham số kiểu và kiểu của các tham số hình thức. **Kiểu trả về và mệnh đề throws không tạo ra một chữ ký khác để overload**, nhưng vẫn là phần quan trọng của hợp đồng và được trình biên dịch kiểm tra khi override hoặc gán lambda.

Ví dụ, nếu interface khai báo phương thức **String convert(String input)**, không thể khai báo thêm một overload chỉ bằng cách đổi kiểu trả về thành **Object**, hoặc chỉ thêm **throws IOException**. Muốn overload, cần khác danh sách tham số theo quy tắc của Java.

## 2. Kiểu tham số

- **Số lượng và thứ tự:** lambda phải nhận đúng số tham số của phương thức SAM và dùng chúng theo đúng thứ tự. **BiFunction&lt;String, Integer, String&gt;** có hai tham số: **String** rồi **Integer**.
- **Kiểu tham số được suy luận:** với biểu thức **s -> s.trim()**, kiểu của **s** được suy luận từ kiểu đích. Có thể ghi tường minh, chẳng hạn **(String s) -> s.trim()**, khi muốn làm rõ kiểu hoặc khi cú pháp yêu cầu.
- **Phương thức triển khai phải khớp:** khi một lớp implement interface hoặc override phương thức, không được thay tham số bằng kiểu rộng hơn hay hẹp hơn. Nếu hợp đồng yêu cầu **load(String id)**, phương thức **load(Object id)** không triển khai hợp đồng đó; nó là một overload khác.
- **Generics:** kiểu tham số còn phụ thuộc vào cách tham số hóa interface. Chẳng hạn **Consumer&lt;String&gt;** nhận **String**, còn **Consumer&lt;Integer&gt;** nhận **Integer**. Trình biên dịch kiểm tra kiểu sau khi áp dụng tham số kiểu phù hợp.

Không nên nhầm việc một kiểu có thể nhận được giá trị của kiểu khác với việc nó có thể thay thế kiểu tham số trong một phương thức override. Quy tắc override yêu cầu tham số tương ứng khớp với chữ ký được override.

## 3. Kiểu trả về

Nếu phương thức SAM trả về giá trị, thân lambda phải tạo ra một giá trị tương thích với kiểu trả về đó. Với thân dạng khối, dùng **return** ở các nhánh có thể kết thúc bình thường. Nếu phương thức SAM trả về **void**, lambda có thể thực hiện một câu lệnh phù hợp mà không trả về giá trị.

Khi override một phương thức:

- Với **kiểu tham chiếu**, kiểu trả về của phương thức triển khai có thể là kiểu con tương thích (*covariant return type*). Ví dụ, phương thức interface trả về **CharSequence** có thể được triển khai bằng phương thức trả về **String**, vì **String** là một **CharSequence**.
- Với **kiểu nguyên thủy**, kiểu trả về phải khớp; không thể đổi **int** thành **long** trong phương thức override.
- Với **void**, phương thức override cũng phải trả về **void**.
- Không thể overload chỉ bằng cách đổi kiểu trả về. Java chọn overload dựa trên danh sách tham số, không dựa trên kiểu trả về.

Với lambda, biểu thức trả về phải tương thích theo quy tắc chuyển đổi kiểu của Java. Ví dụ, lambda có thể trả về một **String** khi kiểu đích yêu cầu **CharSequence**.

## 4. Checked exception trong hợp đồng

Checked exception là ngoại lệ mà trình biên dịch yêu cầu mã xử lý bằng **try/catch** hoặc khai báo tiếp bằng **throws**. Mệnh đề **throws** không xử lý ngoại lệ; nó công bố ngoại lệ có thể truyền đến bên gọi.

### Quy tắc khi triển khai hoặc override

Giả sử phương thức interface khai báo **throws IOException**:

- Phương thức triển khai có thể khai báo **throws IOException**.
- Có thể khai báo một checked exception hẹp hơn, chẳng hạn **FileNotFoundException**, vì nó là lớp con của **IOException**.
- Có thể bỏ mệnh đề **throws** nếu phương thức triển khai không cần để checked exception nào truyền ra.
- Không được khai báo một checked exception rộng hơn như **Exception**, hoặc một checked exception không tương thích như **SQLException**.
- Có thể phát sinh **RuntimeException** hoặc lớp con của nó mà không cần khai báo trong **throws**, vì đây là unchecked exception.

Nếu phương thức interface không khai báo checked exception, phương thức override không thể tự thêm checked exception mới vào hợp đồng. Quy tắc này giúp bên gọi tiếp tục sử dụng interface mà không phải xử lý những ngoại lệ mới mà hợp đồng ban đầu không hứa hẹn.

### Quy tắc với lambda và method reference

Lambda không có cú pháp **throws** riêng. Các checked exception có thể thoát ra từ thân lambda phải tương thích với mệnh đề **throws** của phương thức SAM, hoặc phải được bắt ngay trong thân lambda. Method reference cũng tuân theo quy tắc này.

Ví dụ, với một functional interface có phương thức **load(String id) throws IOException**, lambda gọi **Files.readString(Path.of(id))** có thể truyền **IOException** ra ngoài. Nhưng cùng lời gọi đó không thể được gán trực tiếp cho **Runnable**, vì **Runnable.run()** không khai báo checked exception. Khi cần dùng API không khai báo checked exception, phải xử lý ngoại lệ trong lambda hoặc chủ động chuyển đổi sang một unchecked exception phù hợp; không nên nuốt ngoại lệ một cách im lặng.

### Bên gọi phải tuân theo kiểu đích

Trình biên dịch kiểm tra lời gọi dựa trên kiểu được khai báo của biến, không dựa trên việc đối tượng thực tế có thể ném ít ngoại lệ hơn. Nếu biến có kiểu **TextLoader** và phương thức SAM khai báo **throws IOException**, bên gọi vẫn phải bắt hoặc khai báo **IOException**, ngay cả khi đối tượng hiện tại là một lớp triển khai không bao giờ ném ngoại lệ đó.

## 5. Ví dụ chạy được trên Java 17+

Lưu mã sau trong tệp **ContractDemo.java**. Ví dụ cho thấy lambda, lớp triển khai có kiểu trả về hiệp biến (**String** thay cho **CharSequence**) và checked exception được khai báo trong hợp đồng.

    import java.io.IOException;
    
    @FunctionalInterface
    interface TextLoader {
        CharSequence load(String id) throws IOException;
    }
    
    final class CachedLoader implements TextLoader {
        @Override
        public String load(String id) {
            return "cached:" + id;
        }
    }
    
    public class ContractDemo {
        public static void main(String[] args) throws IOException {
            TextLoader lambda = id -> "lambda:" + id;
            TextLoader cached = new CachedLoader();
            TextLoader checked = id -> {
                if (id.isBlank()) {
                    throw new IOException("empty id");
                }
                return "loaded:" + id;
            };
    
            System.out.println(lambda.load("A-1"));
            System.out.println(cached.load("B-2"));
            try {
                checked.load("");
            } catch (IOException e) {
                System.out.println("checked: " + e.getMessage());
            }
        }
    }

Biên dịch và chạy:

    javac ContractDemo.java
    java ContractDemo

Kết quả chuẩn (stdout):

    lambda:A-1
    cached:B-2
    checked: empty id

Lời gọi **lambda.load(...)** và **cached.load(...)** vẫn được viết trong **main** có **throws IOException**, vì kiểu khai báo của cả hai biến là **TextLoader**. Lớp **CachedLoader** được phép bỏ **throws**, nhưng điều đó không thay đổi hợp đồng nhìn thấy qua kiểu interface. Lambda **checked** có thể ném **IOException** vì SAM đã khai báo ngoại lệ này; bên gọi bắt ngoại lệ và in thông báo.

## 6. Những cách triển khai không hợp lệ

Với **TextLoader** ở ví dụ trên, các khai báo sau không hợp lệ:

    // Sai: Object rộng hơn CharSequence.
    // @Override public Object load(String id) { return id; }

    // Sai: tham số Object không override load(String).
    // @Override public CharSequence load(Object id) { return id.toString(); }

    // Sai: Exception rộng hơn IOException.
    // @Override public CharSequence load(String id) throws Exception { return id; }

Ngược lại, những cách sau phù hợp với hợp đồng:

    // Kiểu trả về String là kiểu con của CharSequence.
    @Override
    public String load(String id) {
        return "value:" + id;
    }

    // Không khai báo throws vẫn hợp lệ.
    @Override
    public CharSequence load(String id) {
        return id;
    }

Các đoạn trên minh họa quy tắc; không đặt tất cả chúng vào cùng một lớp vì sẽ tạo ra các khai báo trùng hoặc xung đột.

## 7. Generics, interface kế thừa và các kiểu hàm có sẵn

- **SAM có tham số kiểu:** một interface như **Decoder&lt;T, E extends Exception&gt;** có thể trả về **T** và khai báo **throws E**. Khi dùng **Decoder&lt;String, IOException&gt;**, kiểu trả về và checked exception được xác định theo các tham số kiểu đã chọn.
- **Nhiều interface cha:** nếu các interface cha khai báo những phương thức trừu tượng có chữ ký tương thích, kiểu trả về phải tương thích với tất cả khai báo liên quan. Phương thức triển khai cũng phải tuân thủ giới hạn checked exception của từng hợp đồng; không thể dùng một **throws** rộng hơn để phá vỡ hợp đồng của một interface cha.
- **Phương thức default:** có phần thân mặc định nhưng vẫn là hành vi công khai của interface; nếu override, lớp triển khai phải tuân theo quy tắc tham số, kiểu trả về và checked exception.
- **Phương thức static và private trong interface:** chúng không phải phương thức trừu tượng SAM mà lớp triển khai phải cài đặt.
- **java.util.function.Function&lt;T, R&gt;:** phương thức **apply** không khai báo checked exception. Vì vậy, không thể truyền thẳng một lambda để ngoại lệ **IOException** thoát ra từ **apply**. Nếu checked exception là một phần cần thiết của API, cân nhắc định nghĩa functional interface riêng có **throws IOException**, hoặc dùng một kiểu hàm khác có hợp đồng ngoại lệ phù hợp, chẳng hạn **Callable&lt;V&gt;** (khai báo **throws Exception**).

## 8. Lỗi thường gặp và cách tự kiểm tra

1. **Đổi kiểu tham số khi override:** hãy kiểm tra chữ ký SAM và bảo đảm kiểu tham số khớp; thay bằng **Object** hoặc một kiểu con không làm phương thức trở thành override hợp lệ.
2. **Cố overload bằng kiểu trả về hoặc throws:** cần một danh sách tham số khác hợp lệ; return type và **throws** không tạo ra overload riêng.
3. **Trả về kiểu quá rộng:** khi override, chọn kiểu trả về tương thích và chỉ dùng kiểu con cho kiểu tham chiếu.
4. **Khai báo checked exception quá rộng:** đối chiếu từng ngoại lệ với mệnh đề **throws** của interface; có thể bỏ hoặc thu hẹp ngoại lệ, nhưng không thể mở rộng tùy ý.
5. **Quên xử lý ngoại lệ ở nơi gọi:** đọc hợp đồng qua kiểu biến và bắt hoặc khai báo các checked exception mà kiểu đó cho phép.
6. **Dùng Function cho API ném checked exception:** xử lý ngoại lệ trong lambda hoặc thiết kế functional interface có mệnh đề **throws** rõ ràng.
7. **Cho rằng throws làm ngoại lệ biến mất:** **throws** chỉ chuyển trách nhiệm xử lý cho bên gọi; chỉ **catch** mới bắt ngoại lệ tại chỗ.

Khi thiết kế hợp đồng hàm, hãy chọn kiểu tham số đủ cụ thể để xác định đầu vào, kiểu trả về thể hiện kết quả hữu ích cho bên gọi và mệnh đề **throws** chỉ công bố những checked exception mà người dùng API thực sự cần biết. Điều này giúp lambda, method reference, lớp triển khai và bên gọi cùng tuân theo một hợp đồng rõ ràng.