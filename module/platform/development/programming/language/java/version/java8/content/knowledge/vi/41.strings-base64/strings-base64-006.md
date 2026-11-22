# Base64 cơ bản, URL-safe và MIME trong Java

## 1. Mục tiêu và bối cảnh

Trong nhiều giao thức, dữ liệu phải đi qua một kênh chỉ chấp nhận tập ký tự hạn chế: JSON, header, tham số URL, email hoặc bản ghi văn bản. **Base64** là cách biểu diễn **các byte bất kỳ** bằng những ký tự ASCII được quy định. Nó dùng các nhóm **6 bit** để chọn một trong 64 ký tự, nhờ đó chuyển dữ liệu nhị phân thành chuỗi tương đối dễ vận chuyển.

Từ Java 8, **java.util.Base64** là API chính thức để mã hóa và giải mã theo ba biến thể:

- **Basic**: bảng chữ cái Base64 tiêu chuẩn theo RFC 4648.
- **URL-safe**: thay những ký tự có thể bất tiện trong URL/tên file bằng ký tự an toàn hơn.
- **MIME**: dòng Base64 tối đa 76 ký tự với CRLF và bộ giải mã nới lỏng để xử lý phần thân email.

Ba biến thể **vẫn được duy trì trong JDK hiện đại**, nên bài này dùng chúng mà không giới thiệu thư viện/hướng dẫn đã legacy. Các chương trình độc lập được kiểm thử với **javac --release 17** và chạy trên Java 17+. Lý thuyết cốt lõi đã có từ Java 8.

Sau bài học, bạn sẽ có khả năng:

1. Giải thích tại sao Base64 là **mã hóa biểu diễn dữ liệu, không phải mã hóa bảo mật**.
2. Hiểu quan hệ **byte[] → Base64 String → byte[]**, khác biệt byte và ký tự Unicode.
3. Chọn đúng Base64.getEncoder/getDecoder, getUrlEncoder/getUrlDecoder, getMimeEncoder/getMimeDecoder.
4. Phân biệt bảng chữ cái **+/ và -_**, dấu padding **=**, dữ liệu có và không có padding.
5. Hiểu output Basic và URL-safe không có line break, còn MIME có thể ngắt sau 76 ký tự bằng CRLF.
6. Sử dụng MIME encoder tùy chỉnh với lineLength và lineSeparator, bao gồm quy tắc làm tròn chiều dài dòng xuống bội số 4.
7. Nhận biết việc MIME decoder bỏ qua ký tự ngoài alphabet và hệ quả bảo mật của decoder quá dễ dãi.
8. Mã hóa văn bản UTF-8, round-trip dữ liệu nhị phân, và xử lý InputStream/OutputStream.
9. Phân biệt việc chấp nhận Base64 không padding với việc chấp nhận padding sai.
10. Viết xử lý lỗi IllegalArgumentException, giới hạn kích thước input và xác thực cấu trúc đầu vào.
11. Hiểu tính thread-safe của Encoder/Decoder, kích thước output và các lưu ý trong sản xuất.

**Phạm vi:** Các ví dụ đều dùng java.util.Base64. Nếu giao thức cụ thể quy định một alphabet, chiều dài, cách padding hoặc canonicalization khác, luôn ưu tiên đặc tả của giao thức đó, không tự giả định một biến thể có thể thay cho biến thể khác.

## 2. Base64 thực hiện điều gì trên bit?

Ba byte là 24 bit. Bộ mã hóa chia 24 bit thành **bốn nhóm, mỗi nhóm 6 bit**; mỗi nhóm tạo một ký tự từ bảng 64 giá trị. Do đó:

~~~text
3 byte = 24 bit
        |
        v
6 bit | 6 bit | 6 bit | 6 bit
  |       |       |       |
  v       v       v       v
  1 ký tự  1 ký tự  1 ký tự  1 ký tự

3 byte đầu vào -> 4 ký tự Base64.
~~~

Nếu còn 1 hoặc 2 byte ở cuối, bộ mã hóa dùng các bit đủ sẵn và **padding bằng dấu =** khi định dạng yêu cầu. Dấu = là dấu đánh dấu phần cuối của nhóm, **không thuộc 64 ký tự dữ liệu**.

| Byte đầu vào còn lại | Ký tự dữ liệu Base64 cuối | Padding chuẩn |
|---:|---:|---:|
| 3 | 4 | 0 |
| 2 | 3 | 1 dấu = |
| 1 | 2 | 2 dấu == |
| 0 | 0 | 0 |

Ví dụ với ASCII:

~~~text
M     -> TQ==
Ma    -> TWE=
Man   -> TWFu
~~~

**Kích thước:** Với N byte, Base64 có padding cần đúng 4 × ceil(N / 3) ký tự, khi không có MIME line breaks. Tăng dung lượng thường xấp xỉ 33,3% đối với input lớn; với input rất nhỏ tỷ lệ có thể cao hơn. MIME còn thêm CRLF nên số byte truyền tải có thể lớn hơn. Base64 không làm dữ liệu nhỏ hơn, không phải compression.

### Base64 không che giấu nội dung

Vì bất kỳ người nào cũng có thể dùng cùng alphabet để giải mã, Base64 **không mang lại tính bí mật, không ngăn chỉnh sửa, không xác thực nguồn gốc**. Nếu cần confidentiality, dùng công nghệ mã hóa được kiểm chứng; nếu cần integrity/authenticity, dùng MAC/chữ ký phù hợp, kiểm soát key và yêu cầu an toàn của giao thức.

Một token trông ngẫu nhiên vì dùng Base64 không có nghĩa token an toàn. An toàn của token phụ thuộc entropy, nguồn tạo, kiểm tra tính hợp lệ, signature/MAC và giao thức xung quanh, không phải lựa chọn dấu + hay -.

## 3. Ba biến thể: Basic, URL-safe và MIME

| Tiêu chí | Basic | URL-safe | MIME |
|---|---|---|---|
| Factory encoder | Base64.getEncoder() | Base64.getUrlEncoder() | Base64.getMimeEncoder() |
| Factory decoder | Base64.getDecoder() | Base64.getUrlDecoder() | Base64.getMimeDecoder() |
| Ký tự ở vị trí 62 | + | - | + |
| Ký tự ở vị trí 63 | / | _ | / |
| Padding mặc định | = khi cần | = khi cần | = khi cần |
| Encoder thêm line break | Không | Không | Tối đa 76 ký tự/dòng, CRLF |
| Decoder chấp nhận ký tự ngoài alphabet | Không | Không | Bỏ qua ký tự ngoài alphabet |
| Ứng dụng thường gặp | Chuỗi/nhị phân qua giao thức cho phép +/ | URL component, tên file, token theo Base64URL | Nội dung MIME/email, dữ liệu dài định dạng nhiều dòng |

**Lưu ý:** Các decoder Basic và URL-safe khác nhau ở bảng chữ cái, nên chúng có thể cùng giải mã một chuỗi nếu chuỗi chỉ dùng các ký tự chung A-Z, a-z, 0-9. Nhưng với ký tự đặc trưng như +/, -_, **không thể mặc nhiên tráo decoder**.

### Chọn biến thể theo giao thức, không chỉ dựa vào nhìn chuỗi

- Một API quy định Base64 RFC 4648 chuẩn: dùng Basic.
- Một giao thức quy định Base64URL không padding: dùng Base64.getUrlEncoder().withoutPadding().
- Một email body theo MIME: dùng MIME, xử lý dòng và CRLF theo đặc tả.
- Nếu dữ liệu đến từ nguồn bên ngoài, **không đoán** bằng cách thử mọi decoder rồi nhận bất kỳ kết quả nào; cách này có thể làm đầu vào mơ hồ và bỏ qua ký tự lỗi.
- Nếu dữ liệu quan trọng cho bảo mật, validate format và canonical representation theo tiêu chuẩn được áp dụng.

## 4. API chính: encoder và decoder

~~~java
// Mảnh mã: cần import java.util.Base64.
Base64.Encoder encoder = Base64.getEncoder();
Base64.Decoder decoder = Base64.getDecoder();

byte[] bytes = new byte[]{1, 2, 3};
String text = encoder.encodeToString(bytes);
byte[] restored = decoder.decode(text);
~~~

- Base64.Encoder.encode(byte[]) trả một byte[] chứa ký tự Base64 ở dạng byte.
- Base64.Encoder.encodeToString(byte[]) trả String dùng bảng ký tự ASCII của scheme.
- Base64.Decoder.decode(String) trả **byte[] khôi phục**, không tự biết đó là text, ảnh hay dữ liệu nhị phân.
- Các phương thức khác hỗ trợ ByteBuffer, mảng đầu ra đã cấp phát và wrapper InputStream/OutputStream.
- Các instance **Base64.Encoder/Decoder an toàn để chia sẻ giữa nhiều thread** theo JavaDoc. Không cần tạo bộ encoder mới cho mỗi request chỉ để tránh race.

**Quan trọng về charset:** Base64 làm việc với **byte**, không trực tiếp với ký tự Unicode. Khi dữ liệu gốc là String, phải chọn một charset rõ ràng như **StandardCharsets.UTF_8**; khi khôi phục, dùng đúng charset đó.

## 5. Ví dụ đầy đủ 1 — mã hóa và giải mã một chuỗi UTF-8

Tạo file **BasicUtf8Demo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class BasicUtf8Demo {
    public static void main(String[] args) {
        String original = "Xin chào Java!";
        byte[] bytes = original.getBytes(StandardCharsets.UTF_8);
        String encoded = Base64.getEncoder().encodeToString(bytes);
        String decoded = new String(
                Base64.getDecoder().decode(encoded), StandardCharsets.UTF_8);
        System.out.println("text=" + original);
        System.out.println("utf8Bytes=" + bytes.length);
        System.out.println("basic=" + encoded);
        System.out.println("decoded=" + decoded);
        System.out.println("emptyLength="
                + Base64.getEncoder().encodeToString(new byte[0]).length());
    }
}
~~~

Chạy:

~~~text
javac --release 17 BasicUtf8Demo.java
java BasicUtf8Demo
~~~

Stdout chính xác trên Java 17:

~~~text
text=Xin chào Java!
utf8Bytes=15
basic=WGluIGNow6BvIEphdmEh
decoded=Xin chào Java!
emptyLength=0
~~~

**Phân tích từng bước:**

1. String gốc gồm các ký tự Unicode. UTF-8 biểu diễn chuỗi bằng **15 byte**, không nhất thiết bằng số ký tự nhìn thấy.
2. getEncoder() mã hóa chính **15 byte UTF-8** và tạo chuỗi Base64 ASCII.
3. getDecoder().decode(encoded) phục hồi byte[] giống byte[] ban đầu.
4. new String(..., UTF_8) dùng đúng charset để trở về tiếng Việt có dấu.
5. Mảng byte rỗng được mã hóa thành chuỗi rỗng, không tạo một dấu =.
6. Không gọi new String(rawBytes) mà thiếu charset, vì charset mặc định từng phụ thuộc môi trường và không thể xem là hợp đồng ổn định khi tương thích nhiều JDK.

**Khi nào không gọi new String sau decode?** Nếu byte[] đại diện cho PNG, PDF, ZIP, serialized protocol message hoặc dữ liệu nhị phân tùy ý, hãy giữ byte[] và gửi vào API xử lý định dạng tương ứng. Ép mọi byte thành UTF-8 String có thể tạo ký tự thay thế và làm hỏng dữ liệu khi encode trở lại.

### Encode/Decode một chuỗi không mã hóa văn bản tự động

~~~java
// Mảnh mã.
byte[] utf8 = input.getBytes(StandardCharsets.UTF_8);
String base64 = Base64.getEncoder().encodeToString(utf8);
String output = new String(Base64.getDecoder().decode(base64),
                           StandardCharsets.UTF_8);
~~~

input là String nguồn của ứng dụng. Base64.Encoder **không có** API nhận String và tự quyết định UTF-8; chính bạn phải chuyển String thành bytes. Sự phân tách này rất quan trọng khi tương tác với hệ thống dùng các charset khác.

## 6. Base64 Basic: bảng chữ cái tiêu chuẩn

Basic dùng 64 ký tự:

~~~text
ABCDEFGHIJKLMNOPQRSTUVWXYZ
abcdefghijklmnopqrstuvwxyz
0123456789+/
~~~

Dấu + và / là một phần **hợp lệ của dữ liệu Base64 chuẩn**, không phải dấu lỗi. Tuy nhiên các ký tự này gây bất tiện trong một số thành phần URL:

- + trong cách mã hóa form-urlencoded có thể bị diễn giải thành **dấu cách**.
- / thường là ký tự phân cách **đường dẫn**.
- = là ký tự padding, đôi khi có thể gây bất tiện cho những giao thức muốn token không có padding.

Vì thế không nên lấy Basic Base64 nhét trực tiếp vào URL path segment hoặc tên file mà bỏ qua quy tắc escaping của URL/file system. Có thể **percent-encode** một giá trị Basic theo đúng ngữ cảnh URL, nhưng nếu giao thức quy định Base64URL thì dùng đúng URL-safe variant.

### Vì sao Basic decoder là strict?

Base64.getDecoder() từ chối ký tự **không thuộc alphabet Base64 cơ bản**, ngoại trừ padding hợp lệ ở cuối. Chẳng hạn:

~~~text
"Zg=="  -> hợp lệ, byte của chữ f
"Zg==\n" -> Basic decoder từ chối vì có newline thừa
"Z!g==" -> Basic decoder từ chối vì dấu ! không hợp lệ
~~~

Không “sửa lỗi” bằng cách âm thầm bỏ mọi dấu câu rồi decode, nhất là khi đầu vào đến từ người dùng hoặc dùng trong token. Làm như vậy có thể chấp nhận dữ liệu sai đặc tả và che giấu lỗi vận chuyển.

## 7. Base64URL và sự khác biệt +/ so với -_

URL-safe Base64 sử dụng **cùng ý tưởng 6 bit/ký tự** nhưng thay:

~~~text
Basic      URL-safe
  +    ->     -
  /    ->     _
~~~

Trong bảng trên, chỉ hai ký tự cuối khác. Các ký tự chữ cái A-Z/a-z và số 0-9 giữ nguyên. **Dấu = vẫn là padding mặc định** của Base64.getUrlEncoder(); muốn bỏ nó phải gọi **withoutPadding()**.

### Cần cặp encoder/decoder tương ứng

~~~java
// Mảnh mã.
String token = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(payloadBytes);
byte[] raw = Base64.getUrlDecoder().decode(token);
~~~

Không dùng Base64.getDecoder() để xử lý một token chứa dấu - hoặc _, bởi decoder Basic không biết hai ký tự đó là ký tự 62/63. Và ngược lại, không dùng URL-safe decoder cho Basic có + hoặc /.

**Lưu ý URL-safe chưa phải là toàn bộ URL escaping.** Nó cung cấp một bảng alphabet tránh + và / cùng các ký tự alphanumeric; còn cấu trúc URL, query parameter, fragment, routing và yêu cầu của giao thức vẫn phải được xử lý đúng. Đặc biệt URL-safe Base64 **không tự chứng minh dữ liệu đã được xác thực hoặc đã ký**.

## 8. Ví dụ đầy đủ 2 — nhìn rõ khác biệt bảng chữ cái

Tạo file **AlphabetVariantsDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Base64;

public class AlphabetVariantsDemo {
    public static void main(String[] args) {
        byte[] bytes = {(byte) 0xFB, (byte) 0xFF, (byte) 0xFE};
        String basic = Base64.getEncoder().encodeToString(bytes);
        String url = Base64.getUrlEncoder().encodeToString(bytes);
        System.out.println("basic=" + basic);
        System.out.println("url=" + url);
        System.out.println("urlHasPlus=" + url.contains("+"));
        System.out.println("sameDecoded="
                + Arrays.equals(Base64.getDecoder().decode(basic),
                                Base64.getUrlDecoder().decode(url)));
        try {
            Base64.getDecoder().decode(url);
        } catch (IllegalArgumentException expected) {
            System.out.println("wrongDecoder=IllegalArgumentException");
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 AlphabetVariantsDemo.java
java AlphabetVariantsDemo
~~~

Stdout:

~~~text
basic=+//+
url=-__-
urlHasPlus=false
sameDecoded=true
wrongDecoder=IllegalArgumentException
~~~

**Giải thích:**

- Ba byte **FB FF FE** được biểu diễn thành +//+ với alphabet Basic.
- Cùng ba byte đó trở thành -__- với alphabet URL-safe.
- Sau khi decode **bằng đúng decoder**, hai mảng byte giống nhau.
- getDecoder() không chấp nhận -_ như ký tự Base64 Basic và ném IllegalArgumentException.
- Dữ liệu không chứa phần dư byte, vì vậy không cần dấu padding; cả hai output dài 4 ký tự.

**Quan trọng:** Với dữ liệu không dùng ký tự thứ 62 hoặc 63, hai output có thể giống hệt nhau. Việc nhìn một token và thấy chỉ chữ/số **không đủ để kết luận** nó thuộc Basic hay URL-safe.
## 9. Padding dấu =: khi nào có, khi nào bỏ?

Base64 biểu diễn 3 byte bằng 4 ký tự. Nếu nhóm cuối không đủ 3 byte, bộ mã hóa chuẩn bổ sung dấu **=** để thành một nhóm 4 ký tự.

~~~text
Số byte còn lại      Basic có padding       Không padding
1                    2 ký tự + ==           2 ký tự
2                    3 ký tự + =            3 ký tự
3                    4 ký tự                4 ký tự
~~~

Ví dụ:

~~~text
M   -> TQ==  -> TQ
Ma  -> TWE=  -> TWE
Man -> TWFu  -> TWFu
~~~

**Dấu = không phải dữ liệu bí mật, cũng không phải lỗi.** Nó chỉ là quy ước về kết thúc nhóm. Một số giao thức quy định phải có padding; một số giao thức như những profile Base64URL nhất định dùng dạng không padding. Chỉ bỏ padding khi giao thức đích cho phép hoặc yêu cầu.

### Dùng withoutPadding() đúng cách

~~~java
// Mảnh mã.
Base64.Encoder noPadding = Base64.getUrlEncoder().withoutPadding();
String text = noPadding.encodeToString(bytes);
~~~

withoutPadding() trả **một Encoder tương đương nhưng không phát dấu =**; nó không thay đổi bảng alphabet, không tự biến Basic thành URL-safe hoặc MIME thành Basic. Ví dụ Base64.getEncoder().withoutPadding() vẫn dùng ký tự +/ chứ không dùng -_.

Nếu data length chia hết cho 3, output vốn không cần dấu =, nên với input như Man, có và không có padding là chuỗi giống hệt nhau.

### Java Decoder chấp nhận thiếu padding ở nhóm cuối

Theo JavaDoc hiện hành, Base64.Decoder chấp nhận padding nhưng **không yêu cầu** nó. Khi nhóm cuối có hai hoặc ba ký tự dữ liệu Base64 mà không có dấu =, decoder xử lý như khi phần padding còn thiếu được bổ sung hợp lệ.

**Điều này không có nghĩa Java chấp nhận mọi chuỗi không có dấu =.**

- Nhóm cuối có 2 ký tự Base64 hợp lệ có thể biểu diễn 1 byte.
- Nhóm cuối có 3 ký tự Base64 hợp lệ có thể biểu diễn 2 byte.
- Chuỗi chỉ có **1 ký tự** không đủ dữ liệu để giải mã và không hợp lệ.
- Nếu đã xuất hiện **một dấu =**, số dấu padding phải đúng; không được để dư hoặc thiếu một cách tùy tiện.
- Decoder Basic và URL-safe vẫn từ chối ký tự không thuộc bảng chữ cái của chính chúng, dù input không có padding.

### Đừng xóa tất cả dấu = trong một chuỗi bất kỳ

Cách dùng string.replace("=", "") có thể che giấu dữ liệu sai định dạng, nhất là khi dấu = nằm giữa dữ liệu hoặc chuỗi chứa nhiều padding sai. Thay vì tự sửa, xác nhận đầu vào hợp lệ theo **format của giao thức**. Nếu cần xuất dạng không padding, tạo output bằng **withoutPadding()** ngay từ encoder.

## 10. Ví dụ đầy đủ 3 — padding, không padding và lỗi dữ liệu

Tạo file **PaddingValidationDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class PaddingValidationDemo {
    public static void main(String[] args) {
        for (String text : new String[]{"M", "Ma", "Man"}) {
            byte[] bytes = text.getBytes(StandardCharsets.US_ASCII);
            String padded = Base64.getEncoder().encodeToString(bytes);
            String unpadded =
                    Base64.getEncoder().withoutPadding().encodeToString(bytes);
            System.out.println(text + "=" + padded + "/" + unpadded);
        }
        System.out.println("decodeUnpadded="
                + new String(Base64.getDecoder().decode("TWE"),
                             StandardCharsets.US_ASCII));
        try {
            Base64.getDecoder().decode("TWE==");
        } catch (IllegalArgumentException expected) {
            System.out.println("badPadding=IllegalArgumentException");
        }
        try {
            Base64.getDecoder().decode("T");
        } catch (IllegalArgumentException expected) {
            System.out.println("oneCharacter=IllegalArgumentException");
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 PaddingValidationDemo.java
java PaddingValidationDemo
~~~

Stdout:

~~~text
M=TQ==/TQ
Ma=TWE=/TWE
Man=TWFu/TWFu
decodeUnpadded=Ma
badPadding=IllegalArgumentException
oneCharacter=IllegalArgumentException
~~~

**Giải thích:**

- M có 1 byte nên cần hai dấu = nếu xuất padded form.
- Ma có 2 byte nên cần một dấu =.
- Man có 3 byte nên không cần padding.
- TWE giải mã thành Ma dù thiếu dấu = ở cuối; Java Decoder cho phép thiếu padding đúng kiểu.
- TWE== không hợp lệ do số dấu = vượt quy tắc của nhóm cuối.
- Một ký tự T không đủ để tái tạo một byte, nên là invalid Base64.
- Các exception được bắt chỉ để trình bày kết quả; trong hệ thống thực, lỗi cần được ghi nhận hoặc chuyển thành lỗi client đúng nghĩa, không phải trả chuỗi rỗng giả vờ thành công.

### Canonical form và chữ ký dữ liệu

Một decoder có thể chấp nhận cả biến thể có padding và không padding, nhưng nếu giao thức đặt yêu cầu **canonical representation** hoặc có quá trình ký/HMAC trên chuỗi encoded, hai chuỗi khác nhau về văn bản có thể **khác nhau khi tính chữ ký**, dù byte giải mã tương đương.

Quy tắc production: xác định chính xác alphabet, padding policy và việc có cho phép dạng thay thế hay không; nếu cần định dạng canonical, **decode rồi re-encode bằng encoder/policy chuẩn, so sánh với input** trước khi chấp nhận, cùng với các kiểm tra khác của giao thức. Không tự coi decoder accept là bằng chứng input đã chuẩn.

## 11. MIME Base64: hỗ trợ nội dung được chia thành dòng

MIME là viết tắt của **Multipurpose Internet Mail Extensions**, một nhóm chuẩn cho nội dung email. Trong một số môi trường truyền dữ liệu theo dòng, output Base64 phải được bọc dòng.

**Base64.getMimeEncoder()** có các đặc tính:

- Dùng cùng alphabet Base64 tiêu chuẩn với Basic, tức ký tự thứ 62/63 là **+/**.
- Dòng output tối đa **76 ký tự Base64**.
- Ngắt dòng dùng hai ký tự **CRLF: \r\n**.
- **Không thêm CRLF vào cuối output**.
- Nếu output không vượt giới hạn 76 ký tự, không có lý do để chèn line break.
- Mỗi dòng đủ dài được chia theo nhóm 4 ký tự, không cắt một nhóm Base64 ngay giữa.

Vì vậy **Basic và MIME có thể phát cùng chuỗi** khi dữ liệu đầu vào ngắn. Sự khác nhau rõ nhất ở dữ liệu đủ dài để MIME bọc dòng.

### MIME decoder có chủ ý nới lỏng

**Base64.getMimeDecoder()** bỏ qua **ký tự không nằm trong alphabet Base64** khi giải mã. Điều này giúp xử lý CRLF và một số dấu phân cách không thuộc alphabet trong dữ liệu MIME, nhưng cũng có nghĩa nó **có thể âm thầm bỏ qua ký tự rác**, không chỉ riêng newline.

Ví dụ:

~~~text
Z m 9 v (không có khoảng trắng) = Zm9v -> foo
Z!m9v -> MIME decoder bỏ qua dấu ! và cho foo
Z!m9v -> Basic decoder từ chối vì có !
~~~

**Rủi ro:** Nếu một API bảo mật nhận Base64 token mà tùy tiện dùng MIME decoder, input chứa ký tự rác có thể được chấp nhận; attacker có thể tạo nhiều dạng văn bản cho cùng dữ liệu. Hãy chọn Basic hoặc URL-safe decoder khi hợp đồng đòi strict alphabet. MIME decoder chỉ nên dùng khi **đúng giao thức MIME hoặc profile cho phép điều đó**.

### MIME encoder có cấu hình

~~~java
// Mảnh mã: muốn mỗi dòng tối đa 12 ký tự, dùng LF separator.
Base64.Encoder encoder = Base64.getMimeEncoder(
        12, new byte[]{'\n'});
~~~

API nhận **lineLength** và **lineSeparator**. Quy tắc:

1. lineLength được làm tròn xuống **bội số 4 gần nhất**.
2. Nếu kết quả sau làm tròn không dương, **không ngắt dòng**.
3. lineSeparator không được chứa một ký tự nào thuộc alphabet Base64 chuẩn; nên dùng separator được giao thức cho phép.
4. Với MIME chuẩn dùng trong email, **CRLF** là lựa chọn đặc tả; tùy chỉnh LF chỉ phù hợp khi hệ thống nhận hỗ trợ, không nên tạo email MIME khác chuẩn tùy tiện.
5. Không có separator ở cuối kết quả, tránh tạo newline dư nếu giao thức yêu cầu đúng nguyên văn.

**Lỗi phổ biến:** Truyền lineLength=10 rồi kỳ vọng 10 ký tự/dòng. Vì 10 làm tròn xuống 8, output sẽ bị bọc dòng sau tối đa 8 ký tự Base64.

## 12. Ví dụ đầy đủ 4 — MIME 76 ký tự, CRLF và decoder nới lỏng

Tạo file **MimeLineDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Base64;

public class MimeLineDemo {
    public static void main(String[] args) {
        byte[] sixty = new byte[60];
        Arrays.fill(sixty, (byte) 'A');
        String basic = Base64.getEncoder().encodeToString(sixty);
        String mime = Base64.getMimeEncoder().encodeToString(sixty);
        String[] lines = mime.split("\r\n", -1);
        System.out.println("basicLength=" + basic.length());
        System.out.println("mimeLength=" + mime.length());
        System.out.println("mimeLineCount=" + lines.length);
        System.out.println("mimeLineLengths="
                + lines[0].length() + "," + lines[1].length());
        System.out.println("trailingCRLF=" + mime.endsWith("\r\n"));
        System.out.println("roundTrip=" + Arrays.equals(sixty,
                Base64.getMimeDecoder().decode(mime)));

        byte[] twelve = new byte[12];
        Arrays.fill(twelve, (byte) 'A');
        String custom = Base64.getMimeEncoder(
                10, new byte[]{'\n'}).encodeToString(twelve);
        System.out.println("custom=" + custom.replace("\n", "|"));
        System.out.println("mimeLiberal="
                + new String(Base64.getMimeDecoder().decode("Z!m9v"),
                             StandardCharsets.US_ASCII));
    }
}
~~~

Chạy:

~~~text
javac --release 17 MimeLineDemo.java
java MimeLineDemo
~~~

Stdout:

~~~text
basicLength=80
mimeLength=82
mimeLineCount=2
mimeLineLengths=76,4
trailingCRLF=false
roundTrip=true
custom=QUFBQUFB|QUFBQUFB
mimeLiberal=foo
~~~

**Phân tích:**

1. 60 byte tạo 80 ký tự Base64: 60 / 3 × 4 = 80.
2. Basic xuất chuỗi 80 ký tự **không ngắt dòng**.
3. MIME chèn đúng một CRLF giữa ký tự thứ 76 và nhóm 4 ký tự cuối: độ dài String là **80 + 2 = 82**.
4. MIME không thêm CRLF vào cuối output, nên trailingCRLF=false.
5. MIME decoder bỏ qua CRLF và tái tạo chính xác 60 byte dữ liệu gốc.
6. Encoder tùy chỉnh với lineLength=10 làm tròn xuống 8; 12 byte có 16 ký tự Base64, được chia **8|8** bằng LF (được thay thành dấu | khi in để dễ nhìn).
7. MIME decoder bỏ qua dấu ! trong Z!m9v và giải mã thành foo — hành vi hữu ích cho dữ liệu MIME nhưng có thể quá dễ dãi với token có yêu cầu strict input.

**Chú ý về output:** Dòng custom có dấu | chỉ vì chương trình **thay LF thành | trước khi in**. Dữ liệu encoded thực tế chứa LF, không chứa |. Khi giao thức cần CRLF, đừng coi ví dụ custom LF là chuẩn email MIME mặc định.

### Khi nào Basic decoder không đọc được MIME data?

Một MIME string được bọc bằng CRLF sẽ chứa các ký tự newline **không có trong alphabet Basic**, vì vậy Base64.getDecoder().decode(mime) sẽ từ chối. Đừng xóa toàn bộ whitespace bằng regex rồi dùng Basic decoder như một thói quen; nếu nguồn thực sự là MIME, dùng MIME decoder và validate cấu trúc envelope theo giao thức.

### MIME decoder không phải parser email

getMimeDecoder() chỉ giải mã **phần dữ liệu Base64**. Nó không phân tích email header, multipart boundary, content disposition, attachment filename hoặc MIME transfer encoding khác. Khi xử lý thư điện tử, dùng MIME parser của thư viện hiện đại tương ứng; chỉ dùng Base64 decoder trên phần nội dung được parser xác định.

## 13. Base64 luôn là byte-to-byte mapping, không phải chuyển đổi charset

Một mảng byte có thể mang bất kỳ giá trị nào từ 0 tới 255, kể cả NUL, ký tự không in được hoặc giá trị không hợp lệ nếu diễn giải theo UTF-8. Base64 không cần biết chúng là dữ liệu gì.

~~~text
byte[] raw
   |             Bộ mã hóa
   +-------------> Base64 String (ASCII)
                              |
                              v
                         Bộ giải mã
                              |
                              v
                         byte[] restored
~~~

Khi byte[] chứa dữ liệu nhị phân, nên kiểm tra round-trip bằng **Arrays.equals(raw,restored)**, không phải so sánh hai String tạo bằng charset không đúng. Cách này giúp tránh phá hỏng byte 0x80, 0xFF và byte 0x00 do chuyển đổi văn bản.

### Dữ liệu Java byte có dấu

Trong Java, kiểu byte là signed [-128..127]. Giá trị 0xFF có thể xuất hiện dưới dạng **-1** khi in Arrays.toString, nhưng bit pattern vẫn là FF. Base64 xử lý byte theo các bit, nên giá trị -1 trong Java không có nghĩa dữ liệu bị lỗi.

### Base64 không có checksum

Nếu một ký tự Base64 được thay thành ký tự khác **vẫn nằm trong alphabet**, decoder có thể tạo ra byte khác **mà không ném exception**. Vì thế decode thành công không chứng minh nội dung còn nguyên. Với tệp hoặc thông điệp quan trọng, sử dụng hash/checksum hoặc cơ chế authentication/integrity theo độ tin cậy cần thiết.

## 14. Ví dụ đầy đủ 5 — round-trip dữ liệu binary

Tạo file **BinaryRoundTripDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Base64;

public class BinaryRoundTripDemo {
    public static void main(String[] args) {
        byte[] raw = {0, 1, 2, 127, (byte) 128, (byte) 255};
        String encoded = Base64.getEncoder().encodeToString(raw);
        byte[] decoded = Base64.getDecoder().decode(encoded);
        System.out.println("base64=" + encoded);
        System.out.println("bytes=" + Arrays.toString(decoded));
        System.out.println("sameBytes=" + Arrays.equals(raw, decoded));
        System.out.println("byteCount=" + decoded.length);
    }
}
~~~

Chạy:

~~~text
javac --release 17 BinaryRoundTripDemo.java
java BinaryRoundTripDemo
~~~

Stdout:

~~~text
base64=AAECf4D/
bytes=[0, 1, 2, 127, -128, -1]
sameBytes=true
byteCount=6
~~~

**Giải thích:**

- Dữ liệu gồm byte 0,1,2,127,128,255; Java in hai byte cuối với signed decimal -128, -1.
- encoded dùng alphabet Basic; ký tự / xuất hiện hợp lệ ở cuối.
- Decoder tái tạo đúng byte[] và Arrays.equals trả true.
- Số byte dữ liệu là 6; encoded có 8 ký tự, đúng công thức 4 × ceil(6/3).
- Không chuyển dữ liệu nhị phân sang String UTF-8 vì không có lý do coi nó là văn bản hợp lệ.

### Khi gửi file, không cần biến dữ liệu nhị phân thành text trước

~~~java
// Mảnh mã, input là mảng byte đọc từ file/ảnh.
String encoded = Base64.getEncoder().encodeToString(input);
byte[] restored = Base64.getDecoder().decode(encoded);
~~~

Đây là cách phù hợp nếu giao thức **yêu cầu nhúng binary trong JSON text** chẳng hạn. Nếu kênh truyền đã hỗ trợ binary trực tiếp (HTTP request body dạng nhị phân, multipart upload, protobuf...), dùng Base64 có thể chỉ làm tăng kích thước và tốn CPU/bộ nhớ không cần thiết.

## 15. Chi phí hiệu năng và bộ nhớ

Giả sử có 30 MB dữ liệu. Khi biểu diễn bằng Base64 chuẩn, kích thước text khoảng 40 MB **chưa tính** overhead String, mảng cấp phát trung gian, object và cấu trúc JSON/HTTP envelope. Trên Java, phương thức encodeToString(byte[]) có thể cấp phát một mảng byte output rồi tạo String; decode(String) thường cấp phát mảng byte khôi phục.

Lựa chọn:

- **Mảng byte + encodeToString**: thuận tiện với dữ liệu nhỏ/vừa và khi cần một String.
- **ByteBuffer**: phù hợp nếu pipeline làm việc bằng buffer; cần hiểu position/limit.
- **Encoder.wrap(OutputStream)** và **Decoder.wrap(InputStream)**: xử lý tuần tự để không buộc toàn bộ dữ liệu phải nằm trong một String lớn.
- **Không tự concat chuỗi Base64 từng chunk** nếu mỗi chunk không nằm đúng ranh giới 3 byte hoặc giao thức không cho ghép như vậy. Ranh giới chunk ảnh hưởng padding, ghép những chuỗi padded tùy ý có thể làm decode sai.
- **Giới hạn kích thước input** trước khi decode dữ liệu không đáng tin; một chuỗi Base64 rất dài có thể cấp phát mảng lớn và gây áp lực bộ nhớ hoặc OutOfMemoryError.

**Ưu tiên sự phù hợp của giao thức.** Không chuyển sang streaming chỉ vì một chuỗi vài trăm byte; nhưng tránh decode toàn bộ attachment lớn vào heap nếu hệ thống có yêu cầu bounded memory.

## 16. Base64 qua InputStream và OutputStream

Java Base64 hỗ trợ streaming với API **Encoder.wrap(OutputStream)** và **Decoder.wrap(InputStream)**:

~~~java
// Mảnh mã, streams được tạo bởi chương trình thực.
OutputStream encodedStream =
        Base64.getEncoder().wrap(destinationOutputStream);

InputStream decodedStream =
        Base64.getDecoder().wrap(encodedSourceInputStream);
~~~

- **Encoder.wrap(OutputStream)** tạo một OutputStream nhận **byte nguồn** và ghi ra các ký tự Base64 vào stream đích.
- **Decoder.wrap(InputStream)** tạo một InputStream đọc **Base64 bytes** từ stream nguồn và cung cấp các byte đã giải mã cho consumer.
- Có thể dùng getMimeEncoder/getMimeDecoder để stream MIME, hoặc getUrlEncoder/getUrlDecoder cho Base64URL.
- Đây là cách xử lý dữ liệu theo dòng, giảm nhu cầu tạo toàn bộ một Base64 String lớn trong bộ nhớ.
- Vẫn phải quản lý **lượng dữ liệu tối đa** chấp nhận: streaming không tự đặt giới hạn số byte đọc hoặc số byte giải mã.

### Vì sao cần close encoder wrapper?

Encoder xử lý **nhóm 3 byte nguồn thành 4 ký tự output**. Khi ghi stream, có thể còn 1 hoặc 2 byte chưa đủ nhóm cuối. Theo JavaDoc, bạn cần **đóng encoder wrapper kịp thời** để nó flush phần byte còn lại, phát padding cần thiết và đóng underlying stream.

Không chỉ gọi flush() rồi giả định đã kết thúc Base64 data hoàn chỉnh; **close()** là điểm hoàn tất của wrapper. Dùng try-with-resources khi bạn sở hữu stream. Cẩn thận rằng đóng wrapper sẽ **đóng luôn stream nền**; nếu stream nền do framework sở hữu hoặc phải tiếp tục dùng, cần thiết kế quyền sở hữu đúng (non-closing wrapper hoặc strategy phù hợp), không close bừa connection/output stream ngoài phạm vi.

### Decoder stream và lỗi dữ liệu

Base64.Decoder.wrap(InputStream) đọc dữ liệu đã mã hóa; nếu gặp nội dung sai scheme, **các phương thức read có thể ném IOException** thay vì IllegalArgumentException thường gặp ở decode(String)/decode(byte[]). Đây là khác biệt quan trọng khi xây dựng xử lý lỗi. Closing decoder wrapper cũng đóng InputStream nền.

Nếu dữ liệu truyền qua mạng bị cắt giữa nhóm Base64, decoder stream có thể báo lỗi ở thời điểm read; chỉ tạo wrapper không có nghĩa input đã được validate. Hãy tiêu thụ đủ dữ liệu và xử lý exception.

## 17. Ví dụ đầy đủ 6 — encode/decode bằng stream

Tạo file **StreamBase64Demo.java**:

~~~java
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class StreamBase64Demo {
    public static void main(String[] args) throws IOException {
        String message = "Xin chào stream!";
        byte[] raw = message.getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream encodedBuffer = new ByteArrayOutputStream();
        try (OutputStream encoded =
                     Base64.getEncoder().wrap(encodedBuffer)) {
            encoded.write(raw);
        }

        byte[] decoded;
        try (InputStream source = new ByteArrayInputStream(
                     encodedBuffer.toByteArray());
             InputStream decodedStream =
                     Base64.getDecoder().wrap(source)) {
            decoded = decodedStream.readAllBytes();
        }

        System.out.println("encoded=" + new String(
                encodedBuffer.toByteArray(), StandardCharsets.US_ASCII));
        System.out.println("decoded=" + new String(
                decoded, StandardCharsets.UTF_8));
        System.out.println("same=" +
                java.util.Arrays.equals(raw, decoded));
    }
}
~~~

Chạy:

~~~text
javac --release 17 StreamBase64Demo.java
java StreamBase64Demo
~~~

Stdout:

~~~text
encoded=WGluIGNow6BvIHN0cmVhbSE=
decoded=Xin chào stream!
same=true
~~~

**Giải thích:**

1. Message gốc được mã hóa bằng UTF-8 sang byte[].
2. OutputStream do Base64.getEncoder().wrap cung cấp nhận byte dữ liệu nguồn và ghi ký tự Base64 vào ByteArrayOutputStream.
3. try-with-resources đóng wrapper; phần dữ liệu cuối và padding được ghi đúng.
4. Decoder.wrap bọc một InputStream chứa **Base64 bytes**, sau đó cung cấp các byte gốc.
5. readAllBytes() dùng trong demo để có stdout dễ kiểm chứng; đối với tệp rất lớn, hãy đọc từng buffer có giới hạn, **đừng dùng readAllBytes nếu mục tiêu là bounded memory**.
6. encodedBuffer là ByteArrayOutputStream để minh họa tiện lợi. Trong sản xuất, có thể dùng file/socket output stream hoặc pipeline stream khác, chú ý quyền sở hữu/close và handling IOException.

### Nếu ghi thành nhiều chunk?

Encoder.wrap có state nội bộ, nên có thể gọi **encoded.write(chunk1)**, **encoded.write(chunk2)**... liên tục trên **cùng wrapper**, sau đó close một lần. Đừng tạo encoder mới cho từng chunk rồi ghép các chuỗi đã được padding; làm vậy có thể xuất hiện dấu = giữa dữ liệu và khiến decoder dừng hoặc báo lỗi.

Tương tự, khi đọc từ Base64.Decoder.wrap(InputStream), consumer nhận byte[] theo các lần read; ranh giới buffer không nhất thiết trùng với ranh giới các nhóm Base64 4 ký tự.

## 18. Base64URL dùng trong URL, token và tên file

URL-safe variant thay + bằng - và / bằng _. Nó không tự chứa ký tự phân cách đường dẫn hay query, nên thường thuận tiện để tạo một đoạn mã mang dữ liệu nhị phân/UTF-8 trong URL.

~~~java
// Mảnh mã:
String text = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(payload.getBytes(StandardCharsets.UTF_8));
~~~

Một số giao thức quy định Base64URL không có padding. Ví dụ có các phần dữ liệu trong token dạng Base64URL, nhưng **việc một đoạn mang định dạng Base64URL không chứng minh token đã được ký, được mã hóa bí mật hoặc được kiểm tra hết hạn**.

### Không sử dụng Base64URL như cơ chế phân quyền

Nhận một chuỗi encoded, decode thành văn bản như uid=42&role=user rồi tin ngay vai trò người dùng là không an toàn. Kẻ tấn công có thể tạo chính một chuỗi encoded khác biểu diễn uid=42&role=admin mà không cần key. Với dữ liệu nhạy cảm, ứng dụng phải có **chữ ký/MAC hợp lệ**, xác thực người dùng và kiểm tra phân quyền trên phía server hoặc một token được chứng thực theo giao thức cụ thể.

### Base64URL vs URL encoding

| Cơ chế | Mục đích | Ví dụ |
|---|---|---|
| Base64 Basic | Biểu diễn bytes thành ASCII, có thể có +/ | getEncoder() |
| Base64URL | Biểu diễn bytes bằng alphabet -_ | getUrlEncoder() |
| Percent-encoding URL | Thoát ký tự trong từng thành phần URL | Phụ thuộc URI/URL component |
| Encryption | Giữ bí mật dữ liệu | Một thuật toán mã hóa có key |
| MAC/chữ ký | Phát hiện sửa nội dung, xác thực nguồn | Cơ chế mật mã được thỏa thuận |

Đừng đánh đồng Base64URL với URLEncoder.encode. Trong Java, java.net.URLEncoder được thiết kế cho form encoding (application/x-www-form-urlencoded), trong đó dấu cách có thể thành +. Quy tắc này **khác** việc chuyển dữ liệu nhị phân thành Base64URL.

## 19. Ví dụ đầy đủ 7 — chứng minh Base64URL không xác thực token

Tạo file **UrlTokenDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class UrlTokenDemo {
    private static String encode(String text) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(
                text.getBytes(StandardCharsets.UTF_8));
    }
    private static String decode(String token) {
        return new String(Base64.getUrlDecoder().decode(token),
                StandardCharsets.UTF_8);
    }

    public static void main(String[] args) {
        String original = "uid=42&role=user";
        String token = encode(original);
        String forged = encode("uid=42&role=admin");
        System.out.println("token=" + token);
        System.out.println("hasPadding=" + token.contains("="));
        System.out.println("decoded=" + decode(token));
        System.out.println("forgedDecoded=" + decode(forged));
        System.out.println("differentTokens=" + !token.equals(forged));
    }
}
~~~

Chạy:

~~~text
javac --release 17 UrlTokenDemo.java
java UrlTokenDemo
~~~

Stdout:

~~~text
token=dWlkPTQyJnJvbGU9dXNlcg
hasPadding=false
decoded=uid=42&role=user
forgedDecoded=uid=42&role=admin
differentTokens=true
~~~

**Diễn giải:**

1. Payload gốc là một đoạn văn bản ASCII nên UTF-8 giữ nguyên các byte tương ứng.
2. Base64URL không padding tạo một chuỗi có ký tự an toàn hơn cho đường dẫn/tên file.
3. Decoder giải mã lại chính payload gốc, không kiểm tra nó có đáng tin cậy hay không.
4. Khi dữ liệu gốc bị thay thành role=admin rồi encode lại, chuỗi khác được tạo ra dễ dàng, và decoder vẫn chấp nhận nó.
5. **Không được đưa role/permission hoặc user ID do client kiểm soát vào quy trình phân quyền chỉ vì chúng được Base64URL.** Cần xác thực nguồn và quyền theo kiến trúc bảo mật.

### Base64URL không tự loại bỏ mọi rủi ro tên file

Dù alphabet tránh + và /, một tên file/đường dẫn vẫn cần xử lý giới hạn độ dài, collision, case sensitivity, ký tự Unicode ở các phần khác, traversal trong những input không phải Base64URL và cấu trúc path của ứng dụng. Không tin tên file do người dùng cung cấp chỉ vì có thể decode.

## 20. Các overload ít gặp: ByteBuffer và mảng đầu ra

Ngoài encodeToString/decode(String), API Base64 hỗ trợ một số tình huống tránh phải tạo một String:

### ByteBuffer

~~~java
// Mảnh mã; ByteBuffer src chứa các byte đầu vào.
ByteBuffer encoded = Base64.getEncoder().encode(src);
ByteBuffer restored = Base64.getDecoder().decode(encoded);
~~~

Theo JavaDoc, hai phương thức này xử lý **các byte remaining của buffer nguồn**, tạo một ByteBuffer mới và cập nhật **position của source tới limit** khi thành công. Không được cho rằng position của source giữ nguyên. Nếu code cần đọc nguồn lại, sử dụng duplicate/slice hoặc đặt lại position đúng theo chính sách.

Khi decode(ByteBuffer) gặp IllegalArgumentException, JavaDoc cho biết source buffer position không bị advance. Nhưng đừng chuyển từ đó sang suy luận rằng mọi API mảng đầu ra có thể rollback một phần dữ liệu đã viết.

### Ghi vào mảng byte đích được cấp phát sẵn

~~~java
// Mảnh mã, dst phải đủ lớn.
int encodedCount = Base64.getEncoder().encode(src, dst);
int decodedCount = Base64.getDecoder().decode(encodedBytes, restored);
~~~

Khác với encode(byte[]) hoặc decode(byte[]) tạo mảng mới, overload nhận byte[] dst cần caller **cấp phát đúng dung lượng**. Nếu mảng không đủ, phương thức ném IllegalArgumentException. Với Decoder.decode(src,dst) mà input sai scheme, JavaDoc cảnh báo **một số byte có thể đã được ghi vào dst trước khi exception được ném**. Vì vậy không dùng buffer đích như dữ liệu đã được kiểm chứng sau một lỗi decode.

### Tính dung lượng và overflow

Với dữ liệu Base64 chuẩn có padding, output text length là 4 × ceil(n/3). Công thức đơn giản cho n nhỏ, nhưng nếu n là int lớn, các phép cộng nhân int thiếu kiểm tra có thể overflow; hãy dùng long/Math.addExact hoặc giới hạn input trước khi cấp mảng. Trong ứng dụng thực, ưu tiên API library hoặc streaming đã được kiểm thử thay vì tự tính kích thước mảng từ input không tin cậy.

### Encoder/Decoder dùng chung được

JavaDoc xác nhận các instance **Base64.Encoder** và **Base64.Decoder** an toàn cho nhiều thread. Có thể giữ static final instance nếu ứng dụng dùng cùng scheme/policy. Tính thread-safe của encoder/decoder **không** làm InputStream/OutputStream hoặc byte[] do bạn cung cấp trở thành thread-safe; khi nhiều thread ghi cùng stream/buffer, bạn vẫn cần đồng bộ và ownership rõ.

## 21. Xử lý lỗi đầu vào và chính sách validate

Nếu đầu vào đến từ request ngoài hệ thống, hãy xác định những điều này **trước khi gọi decode**:

1. Giao thức dùng **Basic, URL-safe hay MIME**?
2. Có bắt buộc padding, cấm padding hay chấp nhận cả hai?
3. Có cho phép newline/whitespace ngoài alphabet không?
4. Có yêu cầu canonical encoding, chiều dài cố định, prefix/header hoặc checksum không?
5. Giới hạn **độ dài chuỗi encoded** và **số byte decoded** là bao nhiêu?
6. Dữ liệu decoded có cần **UTF-8 hợp lệ**, JSON hợp lệ, kích thước tệp, MIME type hay magic bytes hợp lệ không?
7. Dữ liệu dùng cho **định danh, quyền truy cập hoặc giao dịch** có chữ ký/MAC, xác thực và authorization riêng chưa?

### Phân loại exception

| Tình huống | Ngoại lệ thường gặp | Cách xử lý |
|---|---|---|
| Base64.decode(String/byte[]) không hợp lệ | IllegalArgumentException | Trả lỗi input và ghi nhận có kiểm soát |
| decode vào dst không đủ | IllegalArgumentException | Cấp đúng dung lượng hoặc dùng overload trả mảng |
| Encoder.getMimeEncoder có lineSeparator không hợp lệ | IllegalArgumentException | Sửa cấu hình separator |
| Decoder.wrap(InputStream).read gặp Base64 sai | IOException | Xử lý lỗi đọc/format của stream |
| Truyền null vào API không nhận null | NullPointerException | Kiểm tra contract input thay vì nuốt lỗi |
| Phải cấp mảng lớn vượt khả năng JVM | OutOfMemoryError | Giới hạn input và ưu tiên streaming |
| Byte[] không phải UTF-8 hợp lệ | Có thể cho ký tự thay thế nếu decode String mặc định | Dùng CharsetDecoder với REPORT nếu cần strict UTF-8 |

**Không bắt OutOfMemoryError để coi như dữ liệu bình thường.** Nó có thể khiến tiến trình không ổn định; giới hạn dữ liệu tại boundary và thiết kế memory budget từ trước. Nếu giao thức cho phép attachment lớn, nên giới hạn byte đọc và dùng streaming hoặc lưu trữ ngoài heap phù hợp.

### Strict UTF-8 khi decoded bytes là text

Một điểm tinh tế: new String(bytes, StandardCharsets.UTF_8) có thể dùng ký tự thay thế cho chuỗi byte UTF-8 sai, thay vì luôn ném exception. Nếu nghiệp vụ yêu cầu UTF-8 hợp lệ **không chấp nhận replacement**, hãy dùng CharsetDecoder với CodingErrorAction.REPORT. Không được nghĩ Base64 Decoder đã xác nhận tính hợp lệ của UTF-8: nó chỉ kiểm tra **Base64 syntax** và khôi phục bytes.

### MIME permissiveness và canonicalization

Một thông điệp như Z!m9v có thể decode thành cùng byte với Zm9v qua MIME decoder. Nếu hệ thống có chữ ký trên văn bản encoded hoặc dùng chuỗi encoded làm cache key, hai chuỗi có thể là **hai giá trị văn bản khác nhau** cho cùng byte decoded. Vì vậy, với input security-sensitive, sử dụng strict variant được giao thức quy định, reject ký tự ngoài alphabet, và kiểm tra canonical form khi cần.

**Đừng biến MIME decoder thành validator chung** cho bất kỳ dữ liệu trông giống Base64. Decoder này thiết kế cho MIME, nơi bỏ qua các ký tự ngoài alphabet là hành vi được quy định.

## 22. Chọn biến thể cho các tình huống thường gặp

| Nhu cầu | Nên chọn | Lưu ý |
|---|---|---|
| Encode byte[] gọn thành String trong JSON | Basic nếu giao thức quy định chuẩn | +/ hợp lệ trong JSON string; không tự URL-encode |
| Nhúng bytes vào URL path/query theo profile Base64URL | URL-safe, không padding nếu đặc tả yêu cầu | Không tạo tính bí mật hoặc integrity |
| Email attachment Base64 theo MIME | MIME encoder/decoder | Chuẩn MIME dùng CRLF và line wrapping |
| Decode một chuỗi Basic nghiêm ngặt | getDecoder() | Từ chối whitespace và ký tự ngoài alphabet |
| Decode Base64URL | getUrlDecoder() | Phải khớp alphabet, padding policy của giao thức |
| Decode phần body MIME có line breaks | getMimeDecoder() | Có thể bỏ qua nhiều ký tự ngoài alphabet |
| Encode/Decode file lớn | wrap(OutputStream/InputStream) | Close đúng, giới hạn kích thước |
| Dữ liệu là UTF-8 text | getBytes(UTF_8), decode rồi new String(...,UTF_8) | Có thể cần strict CharsetDecoder |
| Dữ liệu nhị phân | Giữ byte[] trước và sau decode | Không ép mọi bytes thành String |
| Secret/token có yêu cầu xác thực | Base64URL chỉ là một lớp biểu diễn | Cần MAC/signature và authorization độc lập |

## 23. Những lỗi thường gặp

### 23.1. Coi Base64 là encryption

Bất kỳ ai có chuỗi encoded đều có thể decode. Không lưu mật khẩu, secret hoặc token quyền lực dưới dạng Base64 rồi coi là an toàn.

### 23.2. Quên charset khi mã hóa String

String.getBytes() không ghi rõ charset dễ gây khác biệt giữa môi trường/JDK cũ; dùng StandardCharsets.UTF_8 và decode cùng charset.

### 23.3. Chuyển binary thành String sau decode

byte[] của ảnh, file nén hoặc payload nhị phân không nhất thiết là UTF-8. new String có thể làm sai dữ liệu nếu encode trở lại.

### 23.4. Dùng Basic encoder cho URL rồi bỏ qua + và /

Ký tự + có thể bị xử lý đặc biệt trong form encoding; / có thể phân tách path. Dùng URL-safe theo giao thức hoặc percent-encode chính xác cho URL component.

### 23.5. Nghĩ URL-safe encoder tự bỏ dấu =

Không. Base64.getUrlEncoder() mặc định có padding khi cần; dùng withoutPadding() nếu profile yêu cầu.

### 23.6. Nghĩ thiếu padding luôn là Base64 sai

Java Decoder chấp nhận nhóm cuối 2 hoặc 3 ký tự thiếu padding; nhưng không chấp nhận nhóm chỉ 1 ký tự hoặc padding sai số lượng.

### 23.7. Xóa hết dấu = để chữa input

Có thể che lỗi dữ liệu hoặc làm input canonical khác nhau. Cấu hình encoder đúng từ đầu, kiểm tra input theo contract.

### 23.8. Dùng MIME decoder như strict validator

MIME bỏ qua ký tự ngoài alphabet; có thể chấp nhận rác ngoài ý muốn. Dùng Basic/URL-safe khi strictness là yêu cầu.

### 23.9. Nghĩ MIME encoder chỉ chèn LF

MIME chuẩn dùng CRLF, dòng tối đa 76 ký tự Base64 và không thêm separator ở cuối.

### 23.10. Kỳ vọng lineLength=10 tạo dòng 10 ký tự

Custom MIME làm tròn xuống bội số 4 gần nhất, nên length=10 tạo dòng dài 8 ký tự.

### 23.11. Dùng getMimeEncoder custom với separator chứa chữ Base64

lineSeparator không được chứa ký tự trong alphabet Base64 Basic; factory sẽ ném IllegalArgumentException. Hãy dùng CRLF theo MIME chuẩn hoặc separator hợp lệ nếu profile cho phép.

### 23.12. Dùng Basic decoder cho MIME nhiều dòng

Basic decoder từ chối CRLF. Dùng getMimeDecoder khi đúng là MIME input; không tự xóa mọi ký tự ngoài alphabet chỉ để decode cho qua.

### 23.13. Không close OutputStream wrapper

Một nhóm byte cuối chưa đủ ba byte có thể chưa được ghi ra hoàn chỉnh cùng padding. Đóng wrapper đúng lúc, đồng thời hiểu việc close wrapper cũng đóng underlying stream.

### 23.14. Ghép các chuỗi Base64 được mã hóa riêng tùy ý

Mỗi chuỗi có thể chứa padding giữa dữ liệu. Nếu muốn stream nhiều chunk, hãy ghi tất cả lên cùng một Encoder.wrap(OutputStream), rồi đóng một lần.

### 23.15. Giải mã chuỗi lớn không giới hạn

decode(String) có thể cấp phát mảng lớn. Với input không tin cậy, giới hạn kích thước, timeout/quota và chọn streaming khi cần.

### 23.16. Cho rằng decode thành công là dữ liệu được bảo toàn/chưa bị sửa

Base64 không có checksum, chữ ký hoặc kiểm tra tính xác thực. Một chuỗi khác vẫn có thể hợp lệ và giải mã thành bytes khác.

### 23.17. Quên validate UTF-8 sau Base64 decode

Base64 decoder không biết byte[] có phải UTF-8 hợp lệ không. Với dữ liệu quan trọng, dùng CharsetDecoder có chế độ REPORT để từ chối chuỗi hỏng.

### 23.18. Tin rằng input được MIME decoder chấp nhận là chuẩn canonical

MIME decoder có thể bỏ qua ký tự ngoài alphabet, dẫn tới nhiều chuỗi input cùng byte decoded. Khi cần chữ ký/cache key, kiểm tra canonicalization đúng policy.

### 23.19. Nghĩ một Base64URL value có chữ ký

Base64URL chỉ chọn alphabet; hoàn toàn có thể tự encode payload khác. Quy trình xác thực phải kiểm tra MAC/chữ ký hợp lệ và quyền ở server.

### 23.20. Quên đóng tài nguyên hoặc xử lý exception khác nhau

decode(String) có thể ném IllegalArgumentException, trong khi Decoder.wrap(InputStream).read có thể ném IOException. Đừng nuốt exception rồi coi dữ liệu rỗng là thành công.

### 23.21. Cho rằng Encoder/Decoder thread-safe thì OutputStream cũng thread-safe

Encoder/Decoder có thể chia sẻ giữa thread; nhưng stream/buffer mutable do ứng dụng cung cấp có thể không an toàn nếu nhiều thread cùng write hoặc thay đổi position.

### 23.22. Dùng Base64 để “nén” dữ liệu

Base64 thường tăng kích thước khoảng 33%, chưa kể line breaks và envelope. Nếu kênh chấp nhận binary, có thể gửi thẳng mà không thêm Base64.

## 24. Checklist trước khi đưa Base64 vào production

- Giao thức quy định Basic, URL-safe hay MIME rõ ràng chưa?
- Có đặc tả padding và có cho phép output không padding chưa?
- Đã dùng getEncoder/getDecoder hoặc getUrlEncoder/getUrlDecoder đúng cặp chưa?
- Nếu dùng MIME, đã xử lý CRLF và chiều dài dòng chuẩn chưa?
- Có lựa chọn đúng strict decoder hoặc MIME permissive decoder không?
- Có validate chiều dài, ký tự được phép, format canonical khi cần không?
- Dữ liệu gốc là String UTF-8 hay byte[] nhị phân?
- Với text quan trọng, có cần strict UTF-8 validation không?
- Có giới hạn bytes decoded, kích thước payload và tài nguyên stream không?
- Có dùng try-with-resources và hiểu wrapper close underlying stream không?
- Nếu chia dữ liệu thành chunk, có dùng cùng một encoder stream thay vì ghép các output đã padding không?
- Có tránh dùng Base64 như encryption, checksum hoặc authentication không?
- Các token và quyền truy cập có MAC/signature và authorization độc lập không?
- Có kiểm tra exception decode, IOException của stream và cleanup không?
- Có test empty input, 1/2/3 byte, Unicode, binary 0x00/0xFF, newline, padding sai và alphabet sai không?
- Nếu dùng Base64 trong URL, có xử lý đúng URL components và dữ liệu không tin cậy không?

## 25. Bài tập và câu hỏi ôn tập

**Câu 1.** Base64 dùng để mã hóa bí mật dữ liệu hay biểu diễn dữ liệu?

*Đáp án:* Biểu diễn bytes bằng ký tự ASCII. Ai cũng có thể giải mã; không có tính bảo mật tự thân.

**Câu 2.** Vì sao từ Man trở thành TWFu và không có dấu =?

*Đáp án:* Man có ba byte, đủ một nhóm 24 bit để tạo bốn ký tự Base64.

**Câu 3.** Tại sao M cần hai dấu = trong dạng padded?

*Đáp án:* M có một byte, chỉ tạo hai ký tự dữ liệu Base64; hai dấu = lấp vị trí còn lại của một nhóm bốn.

**Câu 4.** Basic khác URL-safe ở ký tự nào?

*Đáp án:* Basic có + và /; URL-safe thay thành - và _.

**Câu 5.** getUrlEncoder() mặc định có bỏ padding không?

*Đáp án:* Không. Muốn bỏ padding, dùng getUrlEncoder().withoutPadding() theo yêu cầu giao thức.

**Câu 6.** Decoder của Java có nhận chuỗi TWE không?

*Đáp án:* Có, giải mã thành Ma dù thiếu dấu = cuối. Nhưng TWE== có padding thừa và không hợp lệ.

**Câu 7.** Tại sao chuỗi chỉ một ký tự T không thể decode?

*Đáp án:* Một ký tự Base64 chỉ mang 6 bit, không đủ tạo một byte dữ liệu.

**Câu 8.** MIME encoder khác Basic encoder như thế nào?

*Đáp án:* Dùng cùng alphabet Basic nhưng có thể ngắt dòng sau tối đa 76 ký tự với CRLF; không thêm CRLF ở cuối.

**Câu 9.** lineLength=10 trong getMimeEncoder custom tạo dòng bao nhiêu ký tự?

*Đáp án:* 8, do làm tròn xuống bội số 4.

**Câu 10.** Vì sao MIME decoder có thể giải mã Z!m9v?

*Đáp án:* Nó bỏ qua dấu ! không thuộc alphabet và giải mã các ký tự còn lại thành foo.

**Câu 11.** Có nên dùng MIME decoder cho token có kiểm tra định dạng chặt không?

*Đáp án:* Không, trừ khi protocol chỉ định. Nó có thể nhận ký tự rác ngoài alphabet mà strict decoder sẽ từ chối.

**Câu 12.** Tại sao mới decode byte[] không đủ để phục hồi text Unicode?

*Đáp án:* Còn phải biết charset gốc; với UTF-8 text dùng new String(bytes, UTF_8).

**Câu 13.** Byte 0xFF có thể in thành -1 trong Java không?

*Đáp án:* Có, vì kiểu byte signed. Base64 vẫn giữ đúng bit pattern khi round-trip.

**Câu 14.** Encode stream xong chỉ flush mà không close có thể có vấn đề gì?

*Đáp án:* Encoder còn phần nhóm byte cuối chưa phát ra đầy đủ; close wrapper hoàn tất và flush các byte còn lại theo contract.

**Câu 15.** Vì sao không ghép các Base64 string được encode từ các chunk tùy ý?

*Đáp án:* Padding có thể xuất hiện giữa chuỗi và các ranh giới nhóm 3 byte bị phá vỡ. Cần một encoder stream duy nhất hoặc chia ở ranh giới được thiết kế đúng.

**Câu 16.** Có thể dùng Base64URL để cấp role=admin cho client mà không ký không?

*Đáp án:* Không. Client có thể thay payload rồi encode lại. Cần token được xác thực và phân quyền ở server.

**Câu 17.** decode(String) báo lỗi bằng exception nào?

*Đáp án:* IllegalArgumentException khi Base64 không hợp lệ; stream decoder có thể ném IOException khi đọc dữ liệu sai.

**Câu 18.** Có nên Base64 hóa ảnh trước khi tải nếu HTTP hỗ trợ binary?

*Đáp án:* Không nhất thiết. Base64 tăng kích thước và chi phí. Dùng khi giao thức cần dữ liệu biểu diễn dạng text.

**Câu 19.** Decoder chấp nhận padding hay không padding có nghĩa mọi dạng đều canonical?

*Đáp án:* Không. Giao thức có thể quy định một dạng duy nhất, cần validate/normalize và kiểm tra canonical form khi cần.

**Câu 20.** Encoder/Decoder dùng chung nhiều thread được không?

*Đáp án:* Được theo JavaDoc, nhưng stream/buffer mutable do caller cung cấp vẫn phải quản lý concurrency riêng.

## 26. Tài liệu chính thức còn được duy trì

- Oracle Java SE 25 — **java.util.Base64**, Basic/URL-safe/MIME: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Base64.html
- Oracle Java SE 25 — **Base64.Encoder**, encode/encodeToString/withoutPadding/wrap: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Base64.Encoder.html
- Oracle Java SE 25 — **Base64.Decoder**, decode, padding và wrap: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Base64.Decoder.html
- IETF — **RFC 4648**, Base16/Base32/Base64, các alphabet và padding: https://www.rfc-editor.org/rfc/rfc4648.html
- IETF — **RFC 2045**, MIME và Content-Transfer-Encoding: https://www.rfc-editor.org/rfc/rfc2045
- Oracle Java SE 25 — **StandardCharsets**, charset UTF-8 và US-ASCII: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/StandardCharsets.html
- Oracle Java SE 25 — **CharsetDecoder**, báo lỗi charset: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetDecoder.html

**Kết luận:** Base64 trong Java mã hóa **bytes** thành ký tự ASCII, không bảo mật nội dung. Dùng **Basic** cho bảng +/, **URL-safe** khi cần -_ trong URL/tên file, và **MIME** cho nội dung được bọc dòng 76 ký tự bằng CRLF. Chọn padding đúng theo giao thức; Java Decoder có thể chấp nhận thiếu padding cuối nhưng không chấp nhận mọi input sai. Khi xử lý dữ liệu nhị phân lớn, dùng stream đúng vòng đời; khi xử lý token không tin cậy, validation, canonicalization, kích thước và cơ chế xác thực phải được thiết kế riêng.