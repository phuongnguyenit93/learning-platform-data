# 19.2. Dùng `jarsigner` để ký, xác minh và kiểm tra cảnh báo ở chế độ `-strict`

## 1. Bài toán và kết quả cần đạt

Khi phát hành một thư viện hoặc ứng dụng dạng JAR, người nhận cần kiểm tra hai điều riêng biệt: **các entry đã ký có bị thay đổi sau khi ký hay không** và **chứng thư của người ký có đáng tin theo chính sách của họ hay không**. JDK cung cấp `keytool` để quản lý khóa/chứng thư và `jarsigner` để ký, xác minh JAR.

Sau bài này, bạn có thể:

1. Giải thích cấu trúc chữ ký JAR và ranh giới giữa *integrity*, *authenticity* và *trust*.
2. Tạo keystore thử nghiệm, ký một JAR bằng khóa riêng rồi xác minh bằng `jarsigner -verify`.
3. Đọc cờ `s`/`m`/`k`, thông tin certificate, timestamp và cảnh báo trong `-verbose -certs`.
4. Dùng `-strict` để phát hiện severe warnings qua exit code, phân biệt lỗi thật với cảnh báo và cấu hình kiểm tra khi phát hành.

**Phạm vi:** ký và xác minh JAR bằng công cụ JDK; chữ ký XML là cơ chế khác, không được thực hiện bằng lệnh `jarsigner` này.

## 2. Chữ ký JAR chứng minh điều gì?

JAR là một archive dựa trên ZIP, thường chứa bytecode `.class`, resources và `META-INF/MANIFEST.MF`. Khi ký, `jarsigner` dùng **private key** của một alias trong keystore; chứng thư X.509 (có public key tương ứng) được đưa vào khối chữ ký để bên nhận có thể kiểm tra chữ ký.

Các thành phần quan trọng:

| Thành phần | Chức năng |
| --- | --- |
| `META-INF/MANIFEST.MF` | Có các section ghi digest của dữ liệu các entry được ký. |
| `META-INF/<SIGNER>.SF` | Chứa digest của manifest hoặc các section manifest; kết nối dữ liệu entry với chữ ký. |
| `META-INF/<SIGNER>.RSA` (hoặc `.DSA`/`.EC`) | Chứa chữ ký số của `.SF` và certificate chain của người ký. |
| Certificate chain | Cung cấp public key/danh tính được khai báo; **không tự động biến thành nguồn đáng tin**. |
| Timestamp token (nếu dùng TSA) | Chứng cứ thời điểm ký do dịch vụ đóng dấu thời gian cung cấp, hỗ trợ kiểm tra sau khi chứng thư hết hạn. |

Luồng kiểm tra ở mức khái niệm:

```text
Private key + dữ liệu JAR
    -> manifest digest của entry
    -> signature file (.SF)
    -> signature block (.RSA/.DSA/.EC)
    -> signed JAR

Người nhận:
    chữ ký block hợp lệ?
    -> digest .SF/manifest hợp lệ?
    -> byte của từng entry đã ký còn khớp?
    -> thuật toán, certificate chain, hạn dùng, chính sách trust phù hợp?
```

**Phân biệt ba kết luận:**

- **Integrity:** nội dung entry đã được ký chưa bị đổi kể từ khi ký.
- **Authentication:** chữ ký khớp public key trong certificate của signer.
- **Trust:** người nhận thực sự chấp nhận signer/certificate chain theo truststore, chính sách cấp phát, mục đích sử dụng, thời hạn và (khi yêu cầu) trạng thái thu hồi. Một JAR có thể xác minh được chữ ký nhưng signer vẫn **self-signed hoặc không đáng tin**.
- Ký JAR **không mã hóa** file, không xác nhận nội dung chương trình là an toàn, không tự bảo vệ các entry được thêm sau khi ký. Nếu tồn tại entry chưa ký, phải xem warning và kiểm tra phạm vi ký.

## 3. Các lệnh và tùy chọn thường dùng

| Công cụ/tùy chọn | Ý nghĩa thực tế |
| --- | --- |
| `keytool -genkeypair` | Tạo cặp khóa và chứng thư trong keystore để làm bài thử. |
| `keytool -list -v` | Xem alias, `Entry type`, fingerprint, chain, validity và extensions. |
| `jarsigner -keystore <path> <jar> <alias>` | Ký JAR bằng private key của alias; không dùng `-signedjar` thì file nguồn có thể bị thay thế. |
| `-signedjar <output.jar>` | Ghi kết quả ra JAR mới, giữ bản unsigned để đối chiếu. |
| `-storetype PKCS12` | Nêu tường minh loại keystore; PKCS12 là mặc định của JDK hiện đại. |
| `-digestalg SHA-256` | Chọn digest cho các entry; khác với thuật toán chữ ký. |
| `-sigalg SHA256withRSA` | Thuật toán ký với khóa RSA trong ví dụ; cần tương thích loại khóa. |
| `-verify` | Kiểm tra chữ ký/digest đã ký của JAR thay vì tạo chữ ký mới. |
| `-verbose`, `-certs` | Hiện từng entry, trạng thái `s/m/k` và thông tin signer/certificate. |
| `-strict` | Biến severe warnings thành **exit code khác 0**; không phải nút “bật thêm mật mã”. |
| `-tsa <URL>` | Nhờ Time Stamping Authority (TSA) cấp timestamp theo RFC 3161 khi ký. |
| `-revCheck` | Yêu cầu kiểm tra revocation (OCSP/CRL) khi ký/xác minh; có thể cần kết nối mạng. |

Có thể kiểm tra công cụ sẵn có qua `java -version`, `javac -version`, `jar --help`, `keytool -help`, `jarsigner -help`. Các ví dụ dưới đây dùng **JDK 17+**, với terminal đặt tại thư mục thực hành trống. Mỗi lệnh dài viết trên **một dòng** để chạy được trong PowerShell, Command Prompt và shell Unix. Giữ nguyên tên file/alias để đối chiếu.

## 4. Thực hành từ JAR chưa ký đến JAR đã ký

### Bước 1 — Tạo class và đóng gói JAR

Tạo file `HelloJar.java`:

```java
public class HelloJar {
    public static void main(String[] args) {
        System.out.println("Hello from JAR");
    }
}
```

Biên dịch, đóng gói với `Main-Class`, rồi chạy thử:

```shell
javac HelloJar.java
jar --create --file hello-unsigned.jar --main-class HelloJar HelloJar.class
java -jar hello-unsigned.jar
```

`stdout` của lệnh `java -jar`:

```text
Hello from JAR
```

`javac` tạo `HelloJar.class`; `jar` đóng gói bytecode và manifest. Nếu không khai báo `--main-class`, `java -jar` sẽ thiếu entry point, nhưng JAR vẫn có thể được ký.

### Bước 2 — Tạo keystore PKCS12 và signer thử nghiệm

```shell
keytool -genkeypair -alias demo-signer -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -validity 365 -dname "CN=Demo JAR Signer, O=Example, C=VN" -ext "KU=digitalSignature" -ext "EKU=codeSigning" -keystore demo-signer.p12 -storetype PKCS12
```

Công cụ hỏi mật khẩu keystore. Trong ví dụ PKCS12 này, khóa riêng sử dụng cùng mật khẩu lưu trữ khi không chỉ định mật khẩu khóa riêng khác. Các trường có nghĩa:

- `-alias demo-signer`: tên entry có private key, phải dùng đúng khi ký.
- `RSA` 3072 bit và `SHA256withRSA`: lựa chọn minh họa tương thích JDK 17+.
- `-validity 365`: chứng thư thử nghiệm có hiệu lực 365 ngày tính theo ngày tạo; không phải thời hạn tự động gia hạn.
- `KU=digitalSignature`, `EKU=codeSigning`: khai báo mục đích ký mã; giá trị extension phải phù hợp với mục đích sử dụng trong môi trường thực.
- Không có CA ký chứng thư ở bước này, nên `keytool` tạo **self-signed certificate**. Đây là chủ ý để quan sát cảnh báo `-strict`, **không phải cấu hình phát hành**.

Xem entry trước khi ký:

```shell
keytool -list -v -keystore demo-signer.p12 -storetype PKCS12 -alias demo-signer
```

Xác nhận `Entry type: PrivateKeyEntry`, alias, certificate chain, fingerprints, thời hạn, `KeyUsage` và `ExtendedKeyUsage`. Giá trị fingerprint, thời gian và phần thông tin cụ thể phụ thuộc lần tạo, không có một output cố định cho tất cả máy. Giữ file `.p12` và mật khẩu ở nơi an toàn; **không commit private key** vào Git.

### Bước 3 — Ký JAR bằng `jarsigner`

```shell
jarsigner -keystore demo-signer.p12 -storetype PKCS12 -digestalg SHA-256 -sigalg SHA256withRSA -signedjar hello-signed.jar hello-unsigned.jar demo-signer
```

Lệnh có dạng `jarsigner [options] jar-file alias`. Nhập mật khẩu khi được hỏi. Kết quả là `hello-signed.jar`; `hello-unsigned.jar` vẫn giữ nguyên. Với signer self-signed và không có TSA, công cụ có thể báo cảnh báo **certificate chain not validated / self-signed** và **no timestamp**. Việc có dòng `jar signed.` không đồng nghĩa đã được mọi bên tin tưởng.

Kiểm tra các entry:

```shell
jar --list --file hello-signed.jar
java -jar hello-signed.jar
```

Danh sách phải có `HelloJar.class`, `META-INF/MANIFEST.MF` và các file chữ ký `META-INF/*.SF`, `META-INF/*.RSA` tương ứng với RSA signer. Chạy ứng dụng vẫn in chính xác:

```text
Hello from JAR
```

Tên file chữ ký phát sinh từ alias nhưng có thể được chuẩn hóa để tuân thủ tên entry chữ ký; hãy xem output thực tế của `jar --list`.

## 5. Xác minh: từ kiểm tra cơ bản đến đọc chi tiết

Chạy theo thứ tự:

```shell
jarsigner -verify hello-signed.jar
jarsigner -verify -verbose -certs hello-signed.jar
jarsigner -verify -strict -verbose -certs hello-signed.jar
```

- `-verify` kiểm tra sự nhất quán chữ ký và digest của các entry thuộc phạm vi ký. Khi kiểm tra mật mã thành công, kết quả thường có `jar verified.`, dù có thể kèm warning.
- `-verbose` liệt kê entry; phần chú giải thường bao gồm `s = signature was verified`, `m = entry is listed in manifest`, `k = at least one certificate was found in keystore`. Ví dụ các cờ `sm` bên cạnh `HelloJar.class` cho biết entry này có chữ ký đã xác minh và được ghi trong manifest. `k` phụ thuộc keystore dùng để đối chiếu, **không tự chứng minh signer được mọi máy tin cậy**.
- `-certs` cùng `-verify -verbose` hiển thị signer DN, certificate chain, ngày hiệu lực, và TSA nếu có. Đọc certificate thực tế thay vì chỉ nhìn thông điệp một dòng.
- Với cặp khóa self-signed ở bước 2, `-strict` **được kỳ vọng trả về exit code khác 0**, thường có bit `4` do `signerSelfSigned`/`chainNotValidated`, mặc dù bytecode chưa hề bị sửa. Kết quả và wording khác nhau tùy phiên bản JDK, cấu hình trust và các warning đồng thời.

Sau lệnh `jarsigner -verify -strict ...`, lấy exit code **ngay lập tức**, trước khi chạy lệnh khác:

```bash
# Bash / zsh (Linux, macOS):
echo $?
```

```powershell
# PowerShell (Windows):
$LASTEXITCODE
```

Ví dụ `jar verified, with signer errors` nghĩa là chữ ký có thể đã xác minh về mặt mật mã nhưng có **severe warning** về signer/điều kiện phát hành. Ngược lại, thông báo lỗi `java.lang.SecurityException` liên quan digest/chữ ký có thể chỉ ra JAR đã bị thay đổi hoặc hỏng, cần coi là **verification failure**.

### Tự kiểm tra đúng signer/alias

Có thể đưa keystore và alias vào lệnh verify:

```shell
jarsigner -verify -strict -verbose -certs -keystore demo-signer.p12 -storetype PKCS12 hello-signed.jar demo-signer
```

Khi cung cấp alias, `jarsigner` kiểm tra chữ ký có phù hợp với certificate thuộc alias đó hay không; thiếu hoặc sai alias/keystore có thể dẫn đến severe warning loại `notSignedByAlias` hoặc `aliasNotInStore`. Tuy nhiên, khớp alias trong một keystore thử nghiệm vẫn **không loại bỏ thực tế certificate là self-signed**. Dùng CA/chính sách trust có kiểm soát khi xác minh artefact phát hành.

## 6. `-strict` thực sự thay đổi điều gì?

Không dùng `-strict`, một số tình huống nguy hiểm chỉ được in thành cảnh báo nhưng lệnh vẫn có thể trả mã `0` nếu phần ký/xác minh không gặp lỗi trực tiếp. Dùng `-strict`, **severe warnings** được phản ánh vào mã thoát để script/CI phát hiện. Nó không sửa certificate, không tải một CA mới, không tự kích hoạt kiểm tra thu hồi và không buộc mọi cảnh báo thông tin thành lỗi.

Bảng mã theo tài liệu `jarsigner` của JDK 21:

| Exit code / bit | Nhóm tình huống | Cách hiểu |
| --- | --- | --- |
| `0` | Không có failure hoặc severe warning | Có thể vẫn còn **informational warnings**, như `noTimestamp`; phải đọc log/chính sách. |
| `1` | `failure` | Lệnh thất bại, lỗi cú pháp/keystore/khóa, hoặc kiểm tra chữ ký/digest thất bại. |
| `4` | `hasExpiredCert`, `notYetValidCert`, `chainNotValidated`, `signerSelfSigned`, `disabledAlg`; một số lỗi hết hạn timestamp | Certificate/chain/thuật toán không đáp ứng yêu cầu nghiêm ngặt. |
| `8` | `badKeyUsage`, `badExtendedKeyUsage`, `badNetscapeCertType` | Extension certificate không cho phép mục đích ký mã. |
| `16` | `hasUnsignedEntry` | Có entry dữ liệu chưa ký, nằm ngoài phạm vi xác minh integrity. |
| `32` | `notSignedByAlias`, `aliasNotInStore` | Signer không khớp alias/keystore được yêu cầu. |
| `64` | `tsaChainNotValidated` | Chuỗi chứng thư của TSA không được xác minh hợp lệ. |

**Mã severe warning là bitmask (OR):** ví dụ `4 | 8 = 12` nếu vừa có vấn đề certificate vừa sai KeyUsage. `1` biểu thị failure; đừng áp dụng phép tách bit như một lời giải thích thay thế cho log failure. Nhiều nguyên nhân cùng nằm trong bit `4`, nên chỉ đọc mã `4` **không xác định được lỗi chính xác**: phải phân tích phần cảnh báo ngay phía trên. Mã và tên warning có thể thay đổi theo JDK; với môi trường thực, đối chiếu tài liệu của chính phiên bản đang sử dụng.

### Warning nghiêm trọng và warning thông tin

**Severe warnings** có thể khiến `-strict` trả khác `0`: signer self-signed, chain không xác minh được, chứng thư hết hạn/chưa có hiệu lực, extension không cho ký mã, thuật toán bị vô hiệu, entry chưa ký, sai alias, TSA chain lỗi.

**Informational warnings** thường **không khiến `-strict` thất bại nếu đứng một mình**:

- `noTimestamp`: chữ ký không kèm timestamp; sau khi chứng thư hết hạn hoặc bị thu hồi trong tương lai, việc chứng minh thời điểm ký có thể trở nên khó hoặc không đạt chính sách.
- `hasExpiringCert`: certificate sắp hết hạn (khoảng sáu tháng theo tài liệu).
- `hasExpiringTsaCert`: chứng thư TSA sắp hết hạn.
- `legacyAlg`: thuật toán cũ sắp không được khuyến nghị/chấp nhận ở tương lai.
- `extraAttributesDetected`: thuộc tính POSIX permission/symlink được giữ lại nhưng không được chữ ký bảo vệ.

Đặc biệt: **`noTimestamp` không có bit severe warning riêng** trong bảng trên. Vì vậy `-strict` trả `0` không chứng tỏ JAR có timestamp. Nếu chính sách phát hành yêu cầu TSA, phải kiểm tra thông tin `Timestamped by`/timestamp của signer trong output.

## 7. Bốn tình huống cần chẩn đoán đúng

### Tình huống A — JAR hợp lệ về digest nhưng signer self-signed

Bạn tạo `demo-signer.p12` bằng `keytool -genkeypair`, ký `hello-unsigned.jar` rồi chạy `-verify -strict`. Nội dung `HelloJar.class` có thể có `s` và `m`; `jar verified` có thể đi kèm `signerSelfSigned` hoặc `chainNotValidated`. Với `-strict` thường xuất hiện bit `4`. Đây là bài học về **trust**, không phải bằng chứng file bị sửa.

Cách xử lý khi phát hành: dùng certificate signing với chain được bên nhận chấp nhận; phân phối/kiểm tra chuỗi chứng thư phù hợp, không xóa cảnh báo chỉ để pipeline xanh.

### Tình huống B — Một entry đã ký bị sửa sau khi ký

Nếu thay byte của `HelloJar.class` trong archive **sau khi ký** mà không ký lại, digest của dữ liệu không khớp manifest đã ký. `jarsigner -verify` có thể báo `SecurityException` hoặc thông báo digest invalid và thất bại. Không nên “sửa manifest tay” hoặc dùng `-strict` như giải pháp: phải **build lại JAR cuối cùng rồi ký lại** bằng khóa hợp lệ.

**Quy tắc pipeline:** compile → test → package → sign → verify → publish. Bất kỳ bước nào thay nội dung JAR sau sign đều đòi hỏi ký/verify lại.

### Tình huống C — Thêm resource sau khi ký

Nếu thêm `extra.txt` vào JAR đã ký mà entry mới chưa có chữ ký, chữ ký của các entry cũ vẫn có thể hợp lệ, song entry mới **không được bảo vệ**. `-verbose` giúp phân biệt entry đã ký và chưa ký; `-strict` có thể phát `hasUnsignedEntry` (bit `16`). Không nhầm “chữ ký cũ còn đúng” với “mọi nội dung hiện có đều đã được ký”.

Khi kiểm tra đóng gói, lưu ý các entry kỹ thuật dưới `META-INF/` và thư mục có thể không có cờ ký theo cách hiển thị thông thường. Tập trung vào entry dữ liệu/class thực tế và cảnh báo của `jarsigner`.

### Tình huống D — Chữ ký không có timestamp

Lệnh ký trong bài cố ý không có `-tsa`, do đó có thể thấy `noTimestamp`. Đây là cảnh báo **informational**. Dùng timestamp từ TSA được tổ chức chấp nhận khi cần chứng minh chữ ký được tạo lúc certificate còn hiệu lực:

```text
jarsigner -keystore <signer-keystore.p12> -storetype PKCS12 -tsa <https://TSA-da-duoc-phe-duyet> -signedjar <signed.jar> <unsigned.jar> <signer-alias>
```

Đây là **cú pháp minh họa**, phải thay mọi placeholder bằng giá trị thực và có TSA hoạt động. Kết nối mạng, certificate của TSA và cấu hình thuật toán là các điều kiện đầu vào. Timestamp hợp lệ **không làm certificate self-signed trở thành đáng tin**, không chữa chữ ký bị sửa và không thay thế việc đánh giá trust chain.

## 8. Quy trình xác minh cho build/CI và phát hành

Trình tự kiểm tra được khuyến nghị cho JAR cuối cùng:

1. **Build và chốt artifact:** sau compile/package không còn bước sửa `.class`, manifest hay tài nguyên.
2. **Ký với khóa phát hành:** private key được bảo vệ (vault/HSM/PKCS11 hoặc cơ chế bí mật phù hợp), alias đúng, chain certificate thích hợp và TSA nếu chính sách yêu cầu.
3. **Verify chính JAR sẽ phát hành:** chạy `jarsigner -verify -strict -verbose -certs <artifact.jar>`; lưu log và exit code ngay khi lệnh kết thúc. Exit code khác `0` là tín hiệu chặn để điều tra.
4. **Đánh giá log ngoài mã thoát:** xem có entry unsigned, signer có đúng người/chứng thư mong đợi, thuật toán có bị disabled/legacy, timestamp có cần thiết, thời hạn/chain có thỏa chính sách, và `-revCheck` có được bật khi yêu cầu hay không.
5. **Chính sách chấp nhận:** chỉ phát hành khi kết luận về integrity, identity/trust và các yêu cầu bổ sung đều đạt. Không xem `jar verified.` riêng lẻ là đủ.

Ví dụ lệnh CI đối với **artifact thực tế đã ký bằng certificate phù hợp**:

```shell
jarsigner -verify -strict -verbose -certs release.jar
```

Script/CI phải kiểm tra exit code của chính lệnh trên và lưu stdout/stderr làm bằng chứng. Nếu policy yêu cầu timestamp hoặc một signer cụ thể, bổ sung kiểm tra có cấu trúc đối với log/certificate/keystore và đối chiếu signer được cho phép; không suy diễn từ `exit 0`. **Không dùng JAR self-signed của bài lab để giả lập kết quả CI production thành công.**

Với `-revCheck`, xác minh có thể cần OCSP/CRL và mạng. Không bật/tắt ngầm mà phải theo chính sách kiểm tra thu hồi của hệ thống. Kiểm soát vòng đời, quyền truy cập, thay mới và thu hồi khóa ký; mật khẩu không nên truyền bằng literal trên command line trong môi trường thật (có thể lộ qua lịch sử lệnh/process list). `jarsigner` hỗ trợ `-storepass:env`/`-storepass:file` trong các cấu hình phù hợp, và cũng có thể nhắc nhập tương tác.

## 9. Lỗi phổ biến và cách sửa

| Hiện tượng | Nguyên nhân có thể | Hành động kiểm tra |
| --- | --- | --- |
| `jarsigner: key associated with ... not a private key` hoặc không tìm thấy alias | Alias sai hoặc entry là trusted certificate thay vì `PrivateKeyEntry` | `keytool -list -v -keystore ... -alias ...`; dùng đúng keystore/alias chứa private key. |
| Lỗi mở keystore/mật khẩu | Sai file, `-storetype`, storepass/keypass hoặc hạn chế provider | Kiểm tra đường dẫn, loại keystore, mật khẩu và nhà cung cấp khóa; không in secret vào log. |
| `jar verified.` nhưng `-strict` báo signer errors | Severe warning về self-signed/chain/cert/unsigned entries | Đọc warning cụ thể và mã bitmask; xử lý theo nguyên nhân, không bỏ `-strict`. |
| `hasUnsignedEntry` | Bổ sung entry sau khi ký hoặc build/ký sai thứ tự | Kiểm tra các entry chưa ký, build hoàn chỉnh rồi ký lại. |
| `invalid ... digest`/`SecurityException` | Entry đã ký thay đổi, hỏng, hoặc chữ ký/manifest không nhất quán | So sánh artifact nguồn; rebuild, ký lại và verify; không sửa chữ ký thủ công. |
| `badKeyUsage` hoặc `badExtendedKeyUsage` | Certificate không được phép dùng cho code signing | Sử dụng certificate có KU/EKU đúng theo chính sách CA. |
| `noTimestamp` | Không dùng TSA khi ký | Nếu policy yêu cầu, ký với TSA được phê duyệt và kiểm tra timestamp sau đó. |
| `disabledAlg` / `legacyAlg` | Thuật toán/key size vi phạm hoặc sắp vi phạm chính sách JDK | Dùng thuật toán/khóa hiện hành; không nới `jdk.jar.disabledAlgorithms` để né kiểm tra. |
| Kết quả khác giữa hai máy | Khác phiên bản JDK, truststore, chính sách thuật toán, thời gian, revocation hoặc certificate chain | Ghi nhận `java -version`, tham số, signer, chain và log; chuẩn hóa môi trường kiểm thử. |

## 10. Câu hỏi tự kiểm tra

1. **`jar verified.` có đủ để tin nhà phát hành không?** Không. Nó nói về xác minh chữ ký/digest; cần đánh giá signer identity, certificate chain, chính sách trust và warnings.
2. **Vì sao ví dụ lab có thể trả `4` trong `-strict`?** Signer được tạo bằng `keytool -genkeypair` là self-signed; `signerSelfSigned` và `chainNotValidated` thuộc nhóm severe bit `4`.
3. **`noTimestamp` có khiến `-strict` trả nonzero không?** Nếu chỉ có `noTimestamp` thì không; đây là informational warning. Policy riêng vẫn có thể từ chối artifact thiếu TSA.
4. **Hai warning cùng lúc sẽ ra mã gì?** Severe warning codes được OR, ví dụ `4` và `8` thành `12`; phải đọc log để xác định từng nguyên nhân.
5. **Thêm `config.properties` sau khi ký có an toàn không?** Không thể mặc định coi là được bảo vệ. Entry mới có thể unsigned dù chữ ký của entry cũ vẫn hợp lệ.
6. **Khi nào dùng `-revCheck`?** Khi chính sách yêu cầu kiểm tra revocation; cần dự liệu OCSP/CRL và kết nối mạng.
7. **Vì sao nên dùng `-signedjar`?** Để có JAR đầu ra riêng và tránh vô tình ghi đè artifact chưa ký, thuận tiện đối chiếu và tái lập.

## 11. Checklist thực hành

- [ ] Tạo `HelloJar.java`, chạy `javac`, đóng gói và chạy `hello-unsigned.jar` thành công.
- [ ] Tạo `demo-signer.p12` bằng `keytool`; xác nhận alias `demo-signer` là `PrivateKeyEntry`.
- [ ] Ký sang `hello-signed.jar`, quan sát hai file chữ ký trong `META-INF` và chạy JAR như trước.
- [ ] Chạy `-verify`, `-verify -verbose -certs` và `-verify -strict -verbose -certs`; đối chiếu cờ `s/m/k` với các entry.
- [ ] Lấy exit code ngay sau `-strict`, nhận diện severe warning self-signed/chain và tách bạch với informational `noTimestamp`.
- [ ] Giải thích được hành vi khi entry đã ký bị sửa hoặc entry mới chưa ký xuất hiện.
- [ ] Đề xuất được luồng build → sign → verify → publish với certificate/trust/TSA đúng chính sách.

**Nguồn đối chiếu theo JDK 21:** [jarsigner command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jarsigner.html) (cấu trúc chữ ký, `-verify`, `-strict`, warning/exit code) và [keytool command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html) (PKCS12, `-genkeypair`, X.509 KU/EKU). Khi triển khai trên JDK khác, kiểm tra tài liệu và cấu hình `java.security` của đúng phiên bản đó.
