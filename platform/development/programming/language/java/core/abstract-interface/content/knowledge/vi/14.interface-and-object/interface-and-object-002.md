# Khai báo equals, hashCode và toString trong hợp đồng interface

Một interface có thể khai báo tường minh ba chữ ký public quen thuộc của Object để làm rõ ý định tài liệu hóa API. Việc khai báo lại không cung cấp thuật toán và cũng không buộc mọi implementation có cùng ngữ nghĩa equality hay cùng định dạng chuỗi.

## 1. Khai báo chữ ký

~~~java
interface EntityContract {
    boolean equals(Object other);
    int hashCode();
    String toString();
}
~~~

Các method interface trên mặc định là public abstract. Chúng không cần thân hàm. Lớp triển khai có thể thừa hưởng các method public phù hợp từ Object mà không phải override chỉ vì interface đã nhắc lại chữ ký.

~~~java
final class Ticket implements EntityContract {
    // Không cần override toString(), equals() hoặc hashCode()
    // nếu hành vi mặc định của Object phù hợp với mục đích lớp.
}
~~~

Hành vi mặc định thường không đủ cho value object hoặc entity nghiệp vụ. Object.equals() mặc định so sánh identity tham chiếu; Object.toString() tạo chuỗi chung phục vụ chẩn đoán. Khi cần so sánh theo dữ liệu hoặc biểu diễn dễ đọc, lớp cụ thể phải định nghĩa rõ logic. Interface chỉ tài liệu hóa kỳ vọng, không tự tạo logic chung.

## 2. Hợp đồng equals

Một implementation equals đúng phải bảo đảm:

| Tính chất | Yêu cầu |
| --- | --- |
| Phản xạ | x.equals(x) là true với x khác null |
| Đối xứng | x.equals(y) và y.equals(x) cho cùng kết quả |
| Bắc cầu | nếu x bằng y và y bằng z thì x bằng z |
| Nhất quán | kết quả không đổi khi dữ liệu dùng để so sánh không đổi |
| Null | x.equals(null) là false |

Phương thức nên kiểm tra kiểu trước khi truy cập dữ liệu của đối tượng kia. Chữ ký để override là equals(Object), không phải equals(Product). Nếu chỉ khai báo equals(Product), đó là overload; lời gọi từ HashSet hoặc HashMap vẫn dùng equals(Object).

## 3. Hợp đồng hashCode

Quy tắc bắt buộc: nếu a.equals(b) là true thì a.hashCode() và b.hashCode() phải bằng nhau. Chiều ngược lại không bắt buộc; va chạm băm là hợp lệ. Khi override equals theo giá trị, thường phải override hashCode dựa trên cùng dữ liệu định nghĩa equality.

HashMap và HashSet dùng hash code để chọn vùng tìm kiếm, rồi dựa vào equals để xác định khóa hoặc phần tử phù hợp. Nếu object được dùng làm khóa mà trường tham gia equality/hash thay đổi, tìm kiếm hoặc xóa phần tử có thể thất bại. Ưu tiên trường bất biến cho equality của khóa. Hash code không phải ID duy nhất và không cần giữ nguyên giữa các lần chạy chương trình.

## 4. Ví dụ chạy được

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

interface EntityContract {
    boolean equals(Object other);
    int hashCode();
    String toString();
}

final class Product implements EntityContract {
    private final String code;
    private final String name;

    Product(String code, String name) {
        this.code = Objects.requireNonNull(code);
        this.name = Objects.requireNonNull(name);
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof Product product
                    && code.equals(product.code));
    }

    @Override
    public int hashCode() {
        return code.hashCode();
    }

    @Override
    public String toString() {
        return "Product{code='" + code + "', name='" + name + "'}";
    }
}

public class ObjectContractDemo {
    public static void main(String[] args) {
        Product first = new Product("P1", "Pen");
        Product sameCode = new Product("P1", "Pencil");
        Product other = new Product("P2", "Pen");

        System.out.println(first == sameCode);
        System.out.println(first.equals(sameCode));
        System.out.println(first.hashCode() == sameCode.hashCode());
        System.out.println(first.equals(other));

        Set<Product> products = new HashSet<>();
        products.add(first);
        products.add(sameCode);
        System.out.println(products.size());
        System.out.println(first);
    }
}
~~~

Kết quả:

~~~text
false
true
true
false
1
Product{code='P1', name='Pen'}
~~~

Product định nghĩa hai sản phẩm có cùng code là bằng nhau, bất kể name. Vì hashCode cũng dựa trên code, hai object equal có cùng hash code và HashSet chỉ giữ một phần tử đại diện. Product là final để không có subtype thay đổi riêng chính sách equality.

## 5. toString là biểu diễn, không phải định dạng dữ liệu

Object.toString() mặc định thường tạo chuỗi gồm tên lớp, ký tự @ và dạng hex của hash code; chuỗi đó không phải bản mô tả nghiệp vụ. Override có thể tạo chuỗi dễ đọc, nhưng Java không yêu cầu chuỗi đó duy nhất hay ổn định để serialization. Không dùng toString() làm giao thức truyền dữ liệu hoặc ID lâu dài trừ khi API đặc tả riêng định dạng đó. Tránh đưa bí mật hoặc dữ liệu nhạy cảm vào chuỗi log.

## 6. Lỗi thường gặp

- Chỉ override equals mà quên hashCode: hai object equal có thể có hash code khác nhau, làm collection hoạt động sai.
- Dùng hashCode bằng nhau để kết luận equals: hai object khác nhau có thể va chạm băm.
- Viết equals(Product) và nghĩ đã override equals(Object): đó là overload.
- Dùng các trường khác nhau cho equals và hashCode: có thể phá quy tắc equal implies same hash.
- Cho rằng khai báo trong interface đã cung cấp logic: chữ ký abstract chỉ nêu method, không định nghĩa semantics.

## 7. Khi nào nên khai báo tường minh?

Nên cân nhắc khi ngữ nghĩa equality hoặc biểu diễn là phần quan trọng của tài liệu interface. Nếu interface chỉ mô tả hành vi đặc thù, khai báo lại ba chữ ký thường không thêm khả năng gọi mới. Trong cả hai trường hợp, tài liệu API phải nói rõ dữ liệu nào quyết định equality và các implementation cần tuân thủ điều gì.

Không viết default equals(Object), default hashCode() hoặc default toString() trong interface. Giới hạn biên dịch và lý do thiết kế được giải thích riêng ở bài về default method và Object.

Tự kiểm tra:
- Nếu a.equals(b) là true, hash code có bắt buộc bằng nhau không? Có.
- Hai hash code bằng nhau có chứng minh equals là true không? Không.
- Interface khai báo String toString() có buộc lớp phải override không? Không nhất thiết; implementation public từ Object có thể đáp ứng.
- Nếu một object đã nằm trong HashSet rồi thay đổi trường equality, chuyện gì có thể xảy ra? HashSet có thể không tìm được phần tử theo hash mới.
