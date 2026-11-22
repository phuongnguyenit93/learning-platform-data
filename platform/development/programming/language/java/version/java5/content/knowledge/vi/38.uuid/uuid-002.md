# Phiên bản và biến thể của UUID

## 1. Hai câu hỏi khác nhau khi nhìn một UUID

UUID là giá trị định danh 128 bit. Khi gặp mã như `d13e4e3b-2c18-4cb0-8abc-0123456789ab`, hình dạng chuỗi chưa đủ để hiểu cách diễn giải dữ liệu bên trong. Cần phân biệt:

| Khái niệm | Câu hỏi được trả lời | API Java |
| --- | --- | --- |
| Biến thể (variant) | Giá trị này thuộc họ bố cục nào? | `variant()` |
| Phiên bản (version) | Trong họ bố cục đang xét, phần dữ liệu được tổ chức theo kiểu nào? | `version()` |

Có thể hình dung variant là quy ước đọc một biểu mẫu, còn version là loại biểu mẫu cụ thể theo quy ước đó. Đọc sai quy ước thì dù tìm thấy một con số “4” cũng chưa thể kết luận giá trị là UUIDv4 đúng hợp đồng.

Trong bài này, trọng tâm là variant IETF thông dụng, các phiên bản còn hữu ích trong hệ thống hiện đại và cách kiểm tra chúng bằng Java. Phần sinh UUID chi tiết và các cơ chế tương thích cũ không thuộc phạm vi bài.

## 2. Nhận diện trong dạng chuỗi chuẩn

Dạng chuỗi UUID có năm nhóm `8-4-4-4-12` chữ số hex. Với variant IETF:

```text
xxxxxxxx-xxxx-Vxxx-Nxxx-xxxxxxxxxxxx
              |    |
           version variant
```

- Chữ số `V` chứa 4 bit version.
- Hai bit đầu của `N` là `10`, chỉ variant IETF.
- Do hai bit còn lại của `N` là dữ liệu, chữ số này có thể là `8`, `9`, `a` hoặc `b`.

Ví dụ:

```text
d13e4e3b-2c18-4cb0-8abc-0123456789ab
              4    8

V = 4     -> version 4
N = 8     -> nhị phân 1000, tiền tố 10
```

Vị trí này thuộc quy ước trong [RFC 9562, mục 4](https://www.rfc-editor.org/rfc/rfc9562.html#section-4). Trong Java, `variant()` trả `2` cho họ có tiền tố `10`. Số `2` này không phải version 2, cũng không phải chữ số đầu nhóm thứ tư.

Từ ví dụ, đổi `8abc` thành `9abc`, `aabc` hoặc `babc` vẫn giữ variant IETF:

```text
8 = 1000
9 = 1001
a = 1010
b = 1011
    ^^
    10 là tiền tố chung
```

Đó là bốn UUID khác nhau vì bit dữ liệu đã thay đổi, dù version và variant của chúng giống nhau. Hai đối tượng có cùng `version()` và `variant()` không nhất thiết có cùng định danh.

## 3. Đọc version để hiểu đúng loại dữ liệu

Các trường hợp đáng phân biệt khi làm việc với hệ thống hiện đại:

| Version | Ý nghĩa chính | Điều cần hiểu trước khi áp dụng |
| --- | --- | --- |
| 4 | Dựa trên dữ liệu ngẫu nhiên hoặc giả ngẫu nhiên | Không chứa trường thời gian để suy thời điểm tạo |
| 6 | Sắp xếp lại dữ liệu thời gian theo mốc Gregorian | Cần đúng quy ước thời gian; không giải mã như version 7 |
| 7 | Dữ liệu thời gian Unix theo mili giây ở đầu | Có lợi cho thứ tự thời gian, nhưng không tự bảo đảm thứ tự nghiệp vụ toàn cục |
| 8 | Bố cục tùy biến trong khung UUID | Cần thỏa thuận riêng về ý nghĩa các bit dữ liệu |

Bảng tập trung vào các lựa chọn và dữ liệu đang có giá trị áp dụng; không phải danh sách đầy đủ mọi số đã được đăng ký. Tham khảo [RFC 9562, các bố cục UUID](https://www.rfc-editor.org/rfc/rfc9562.html#section-5).

Version không nói rằng ứng dụng đang chạy Java phiên bản nào, không phải số lần bản ghi được sửa và cũng không thể dùng thay trường “phiên bản đơn hàng”.

Một số hệ quả thực tế:

- Nếu hợp đồng API yêu cầu UUIDv4, mã có version 7 phải bị từ chối theo hợp đồng đó, dù vẫn là UUID hợp lệ.
- Nếu hợp đồng chỉ yêu cầu một UUID thuộc variant IETF, tự thêm điều kiện version 4 có thể làm mất khả năng tích hợp với bên dùng version 7.
- Nếu cần biết thời điểm tạo bản ghi, lưu trường thời gian nghiệp vụ rõ ràng. Việc đọc thời gian từ một UUID có hỗ trợ không thay thế thông tin “bản ghi được tạo khi nào” của hệ thống.
- Với version 8, chỉ nhìn số 8 không đủ để biết dữ liệu có thời gian, số thứ tự hay nội dung tùy biến nào.

Không được “đổi version” bằng cách thay chữ số trong chuỗi. Chẳng hạn, sửa chữ số `4` thành `7` chỉ đổi một phần giá trị. Nó không chuyển những bit ngẫu nhiên thành thời gian đúng, không thực hiện thuật toán sinh UUIDv7 và làm định danh ban đầu biến mất.

## 4. API Java biểu diễn được và API Java sinh được là hai khả năng riêng

Trong Java 17/21:

- `UUID.fromString(text)` đọc giá trị từ chuỗi.
- `version()` và `variant()` cho phép khảo sát các bit phân loại.
- `UUID.randomUUID()` tạo UUIDv4, không chọn ngẫu nhiên giữa các version.
- Việc đọc được UUIDv7 không có nghĩa lớp `UUID` ở các phiên bản Java này có sẵn hàm sinh UUIDv7.
- `timestamp()` không phải hàm giải mã thời gian dùng chung cho mọi UUID; với UUIDv7 trong ví dụ, nó ném `UnsupportedOperationException`.

Các hợp đồng phương thức này nằm trong [Java UUID API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/UUID.html). Khi cần bộ sinh một version khác, phải kiểm tra cụ thể thư viện và phiên bản JDK đang dùng, không suy từ việc parser đã đọc được mã.

Quan trọng hơn, một phương thức đọc bit không kiểm chứng nguồn gốc giá trị. Một người có thể tự viết chuỗi mang version 4 và variant IETF. Vì vậy, kết quả `4/2` không chứng minh rằng mã được sinh bằng bộ sinh ngẫu nhiên tốt hoặc chưa từng xuất hiện trước đó.

## 5. Nil và Max: hai giá trị đặc biệt cần xử lý theo hợp đồng

Hai giá trị dễ làm điều kiện kiểm tra đơn giản bị hiểu sai:

```text
Nil: 00000000-0000-0000-0000-000000000000
Max: ffffffff-ffff-ffff-ffff-ffffffffffff
```

Nil có toàn bộ bit bằng 0; Max có toàn bộ bit bằng 1. Đây là các giá trị đặc biệt trong [RFC 9562, mục 5.9–5.10](https://www.rfc-editor.org/rfc/rfc9562.html#section-5.9).

Java vẫn biểu diễn được chúng. Khi khảo sát bit:

| Giá trị | `version()` | `variant()` |
| --- | ---: | ---: |
| Nil | 0 | 0 |
| Max | 15 | 7 |

Các số này là kết quả đọc bit, không phải khẳng định “version 0” và “version 15” là hai bộ sinh UUID thông thường nên sử dụng.

Nếu một API định nghĩa Nil để biểu diễn “chưa gán”, xử lý đúng quy tắc đó trước khi áp điều kiện cho định danh thật. Nếu API không quy định như vậy, đừng tự gán nghĩa cho Nil hoặc Max. Cũng không đồng nhất Nil với `null`: Nil là một giá trị UUID cụ thể, còn `null` là không có tham chiếu đối tượng.

## 6. Chương trình Java chạy đầy đủ

Lưu thành `UuidKindsDemo.java`. Chương trình dùng API Java 17 trở lên, không cần thư viện ngoài:

```java
import java.util.UUID;

public class UuidKindsDemo {
    public static void main(String[] args) {
        UUID v4 = UUID.fromString("d13e4e3b-2c18-4cb0-8abc-0123456789ab");
        UUID v7 = UUID.fromString("01900000-0000-7abc-8def-0123456789ab");
        UUID nil = new UUID(0L, 0L);
        UUID max = new UUID(-1L, -1L);

        show("v4", v4);
        show("v7", v7);
        show("nil", nil);
        show("max", max);

        for (String first : new String[] {"8", "9", "a", "b"}) {
            UUID id = UUID.fromString(
                    "d13e4e3b-2c18-4cb0-" + first + "abc-0123456789ab");
            System.out.println("group4=" + first + " -> variant=" + id.variant());
        }

        System.out.println("acceptV4(v4)=" + acceptsV4(v4));
        System.out.println("acceptV4(v7)=" + acceptsV4(v7));
        System.out.println("acceptV4(nil)=" + acceptsV4(nil));
        System.out.println("acceptV4(max)=" + acceptsV4(max));
        System.out.println("acceptV4(null)=" + acceptsV4(null));

        UUID generated = UUID.randomUUID();
        System.out.println("generated=" + generated.version() + "/" + generated.variant());

        try {
            v7.timestamp();
        } catch (UnsupportedOperationException ex) {
            System.out.println("v7.timestamp=unsupported");
        }
    }

    private static void show(String label, UUID id) {
        System.out.println(label + ": version=" + id.version()
                + ", variant=" + id.variant());
    }

    private static boolean acceptsV4(UUID id) {
        return id != null && id.variant() == 2 && id.version() == 4;
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 UuidKindsDemo.java
java UuidKindsDemo
```

Stdout:

```text
v4: version=4, variant=2
v7: version=7, variant=2
nil: version=0, variant=0
max: version=15, variant=7
group4=8 -> variant=2
group4=9 -> variant=2
group4=a -> variant=2
group4=b -> variant=2
acceptV4(v4)=true
acceptV4(v7)=false
acceptV4(nil)=false
acceptV4(max)=false
acceptV4(null)=false
generated=4/2
v7.timestamp=unsupported
```

Chương trình có ba mục đích:

1. So sánh các giá trị cố định để kết quả dễ kiểm chứng. Hai chuỗi `v4` và `v7` là dữ liệu minh họa đọc bit; chúng không được giới thiệu như bằng chứng một bộ sinh đã hoạt động đúng.
2. Cho thấy `8/9/a/b` ở đầu nhóm thứ tư đều dẫn tới cùng `variant() == 2`.
3. Minh họa chính sách riêng `acceptsV4()`: nhận đúng variant IETF và version 4, đồng thời không lỗi khi đầu vào là `null`.

Dòng `generated=4/2` ổn định vì chỉ in loại UUID, không in mã vừa sinh. Mỗi lần gọi `randomUUID()` thường cho giá trị khác nhau; không nên viết kiểm thử yêu cầu hai lần gọi luôn bằng nhau hoặc coi vài lần không trùng là bằng chứng tuyệt đối về tính duy nhất.

Khối `try/catch` dùng để minh chứng giới hạn của `timestamp()`, không phải mẫu khuyến khích xử lý mọi UUID bằng cách gọi thử rồi bắt lỗi. Trong mã thật, trước hết hãy biết version và hợp đồng dữ liệu cần đọc.

## 7. Từ đọc bit đến kiểm tra dữ liệu đầu vào

Một luồng xử lý rõ ràng có thể gồm:

1. Xác định hợp đồng chuỗi: có yêu cầu dạng chuẩn 36 ký tự hay không?
2. Chuyển chuỗi thành UUID và xử lý lỗi cú pháp.
3. Xử lý giá trị đặc biệt nếu hợp đồng cho phép.
4. Kiểm tra variant và tập version được chấp nhận.
5. Tra cứu bản ghi và kiểm tra quyền của người gọi.

Đây là các lớp trách nhiệm khác nhau. Hàm `acceptsV4()` trong ví dụ chỉ thực hiện một chính sách ở bước 4; nó không kiểm tra chuỗi gốc, không truy vấn cơ sở dữ liệu và không cấp quyền truy cập.

Chẳng hạn, một mã đơn hàng hoàn toàn đúng version/variant vẫn có thể không tồn tại, hoặc thuộc về tài khoản khác. Ngược lại, UUIDv7 không phải dữ liệu hỏng chỉ vì một hệ thống cũ của bạn đang giới hạn đầu vào ở version 4; khi đó vấn đề nằm ở hợp đồng tích hợp cần được quyết định rõ.

## 8. Lỗi phổ biến và bài tập

| Lỗi | Cách sửa cách hiểu |
| --- | --- |
| “variant 2” nghĩa là UUID version 2 | Đọc riêng `variant()` và `version()` |
| Nhìn thấy `a` ở nhóm thứ tư nên kết luận variant 10 | `a` là cả bốn bit; variant IETF được nhận diện bằng hai bit đầu `10` |
| Tất cả UUID đều có thời gian | Chỉ diễn giải trường dữ liệu theo đúng version |
| Parser đọc được thì bộ sinh tương ứng có sẵn | Kiểm tra riêng khả năng đọc và sinh của API |
| Có version 4 thì chắc chắn là mã được sinh ngẫu nhiên tốt | Bit đánh dấu không chứng minh chất lượng hoặc nguồn gốc bộ sinh |
| Nil là `null` | Nil là giá trị 128 bit cụ thể; `null` là không có tham chiếu |
| Đổi chữ số version là chuyển đổi được thuật toán | Sửa bit tạo mã khác, không thực hiện thuật toán sinh |

Tự kiểm tra:

1. Hai UUID có cùng version 4 và variant 2 có bắt buộc bằng nhau không?
2. Với `01900000-0000-7abc-bdef-0123456789ab`, version và kết quả `variant()` là gì?
3. Vì sao từ chối UUIDv7 có thể là đúng hợp đồng của một API nhưng không phải bằng chứng UUIDv7 sai chuẩn?
4. Nếu người dùng tự sửa một mã để vượt điều kiện `acceptsV4()`, hàm có kiểm chứng được lịch sử sinh mã không?

Đáp án: (1) không, phần dữ liệu còn lại có thể khác; (2) version 7, variant 2 vì `b = 1011`; (3) chuẩn biểu diễn và chính sách API là hai lớp riêng; (4) không, hàm chỉ kiểm tra những bit hiện có.
