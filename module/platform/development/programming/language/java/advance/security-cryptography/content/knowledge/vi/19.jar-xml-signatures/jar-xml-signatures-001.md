# 19.1 — Chữ ký JAR, manifest, digest của entry và chuỗi chứng thư người ký

## Mục tiêu

Sau bài này, bạn có thể giải thích chữ ký số trong Java Archive (JAR) bảo vệ phần nào của gói, đọc được các tệp `META-INF/MANIFEST.MF`, `*.SF` và `*.RSA`/`*.EC`, phân biệt tính toàn vẹn với độ tin cậy của người ký, ký và kiểm tra một JAR bằng JDK 17+, và lấy thông tin người ký của từng entry qua API Java.

Phạm vi ở đây là **JAR signing**. Chữ ký XML là cơ chế khác và không nằm trong bài 19.1.

## 1. JAR được ký là gì?

JAR là một tệp lưu trữ theo định dạng ZIP chứa `.class`, resource và các mục siêu dữ liệu. Mỗi tệp hoặc thư mục bên trong gọi là một **entry**; ví dụ `com/example/App.class` hoặc `config/default.properties`.

Ký JAR dùng **khóa riêng** của người ký tạo chữ ký số, còn người kiểm tra dùng **khóa công khai** trong chứng thư để xác minh chữ ký. Cơ chế gắn các digest của dữ liệu JAR với chữ ký đó, từ đó giúp phát hiện việc thay đổi các entry đã ký.

Ba điều phải tách riêng:

- **Integrity (toàn vẹn):** các byte của một entry được ký có còn đúng như khi ký không?
- **Authenticity (xác thực chữ ký):** chữ ký có được tạo bởi khóa riêng tương ứng với khóa công khai trong chứng thư người ký không?
- **Trust (tin cậy):** chứng thư người ký có được hệ thống của bạn chấp nhận, được cấp đúng mục đích, còn hiệu lực và phù hợp chính sách không?

Một chữ ký hợp lệ **không tự chứng minh** mã nguồn an toàn, người ký đáng tin, hay toàn bộ entry trong JAR đều đã được ký. Java không tự coi mọi JAR có chữ ký là được phép chạy với quyền cao hơn.

## 2. Ba lớp liên kết nội dung với chữ ký

JAR ký thông thường có những tệp quan trọng sau:

| Thành phần | Chứa gì? | Vai trò |
| --- | --- | --- |
| `META-INF/MANIFEST.MF` | Thuộc tính chính và các section `Name: ...`, `SHA-256-Digest: ...` của entry | Liên kết **byte nội dung từng entry** với digest |
| `META-INF/JAR-DEMO.SF` (tên chỉ minh họa) | `Signature-Version`, digest của manifest và/hoặc digest của các section manifest | Liên kết **manifest** với dữ liệu sắp được ký |
| `META-INF/JAR-DEMO.RSA`, `.EC` hoặc `.DSA` | Signature block dạng nhị phân, chữ ký trên tệp `.SF` và thông tin chứng thư liên quan | Liên kết **`.SF`** với khóa của người ký |
| Entry ứng dụng | Ví dụ `Hello.class`, tài nguyên, cấu hình | Dữ liệu được kiểm tra đối chiếu digest khi đọc |

Tên `JAR-DEMO` phụ thuộc alias hoặc tùy chọn `-sigfile`, không phải tên cố định. Một JAR có thể có nhiều cặp `.SF` và signature block do nhiều người ký.

Sơ đồ logic:

~~~text
Byte của Hello.class
       │ SHA-256
       ▼
MANIFEST.MF: section Name: Hello.class + SHA-256-Digest
       │ digest của section manifest (và có thể cả manifest)
       ▼
JAR-DEMO.SF: các digest về manifest
       │ ký bằng private key
       ▼
JAR-DEMO.RSA: chữ ký của .SF + chứng thư người ký
       │
       ▼
Verifier dùng public key trong chứng thư xác minh chữ ký,
rồi đối chiếu .SF → manifest → byte thực của Hello.class
~~~

**Digest không phải chữ ký.** Digest là kết quả hàm băm, ai cũng có thể tính lại khi sửa file. Chữ ký số mới ràng buộc các digest đó với khóa riêng của người ký.

## 3. Manifest và digest của từng entry

`META-INF/MANIFEST.MF` có main section ở đầu, tiếp theo là các section riêng, ngăn nhau bởi dòng trống:

- Main section có `Manifest-Version: 1.0` và có thể có `Main-Class`, `Class-Path` hay các thuộc tính đóng gói khác.
- Section của entry bắt đầu bằng `Name: đường/dẫn/trong/jar`, sau đó có thể có `SHA-256-Digest`, `SHA-384-Digest` hoặc thuật toán khác tùy phiên bản/cấu hình.
- Giá trị digest là Base64 của **các byte nội dung entry sau khi giải nén**, không phải Base64 của tên tệp, không phải hash của toàn bộ JAR và không phải chữ ký bằng private key.

Có thể biểu diễn cách tính bằng công thức:

~~~text
entryDigest = Base64(SHA-256(uncompressedEntryBytes))
~~~

Ví dụ một section được nhận diện bởi `Name: Hello.class`; trường `SHA-256-Digest` tương ứng được `jarsigner` tạo từ byte của `Hello.class`. Không tự điền một chuỗi hash bất kỳ: verifier so sánh với digest tính từ byte thực tế.

**Định dạng là một phần của cơ chế.** Manifest là văn bản theo quy tắc riêng: thuộc tính dạng `Key: Value`, các section phân cách bằng dòng trống, dòng dài được tiếp nối bằng một dòng bắt đầu bằng khoảng trắng, và có giới hạn 72 byte cho mỗi dòng vật lý. Các byte, cách xuống dòng và biểu diễn section liên quan đến phép băm của `.SF`; vì vậy sửa manifest bằng công cụ formatter hoặc đổi encoding/xuống dòng sau khi ký có thể làm xác minh thất bại.

Không phải mọi entry có mặt trong JAR đều nhất thiết có section được ký. Với `jarsigner`, các file entry hiện có thông thường được ký (ngoại trừ tệp metadata chữ ký dành riêng). API ký cấp thấp có thể chỉ ký một tập con; entry mới được thêm vào sau khi ký cũng có thể không nằm trong phạm vi chữ ký trước đó.

## 4. Tệp `.SF` bảo vệ manifest như thế nào?

Tệp `META-INF/<tên>.SF` là **signature file**, nhưng **không phải** bản chữ ký nhị phân. Nó chứa các digest dùng để kiểm tra manifest:

- `Signature-Version: 1.0` xác định phiên bản signature file.
- `SHA-256-Digest-Manifest` (nếu có) là digest của toàn bộ manifest.
- `SHA-256-Digest-Manifest-Main-Attributes` (nếu có) là digest của main attributes của manifest.
- Mỗi section `Name: Hello.class` trong `.SF` chứa digest của **section tương ứng trong manifest**, khác với digest của nội dung `Hello.class` nằm trong manifest.

Ví dụ, hai trường cùng tên `SHA-256-Digest` nhưng ở hai tầng khác nhau có ý nghĩa khác:

| Trường | Dữ liệu được băm |
| --- | --- |
| `MANIFEST.MF` → `Name: Hello.class` → `SHA-256-Digest` | Byte nội dung `Hello.class` |
| `JAR-DEMO.SF` → `Name: Hello.class` → `SHA-256-Digest` | Byte của section `Hello.class` trong `MANIFEST.MF` |

Verifier thường thử digest của toàn bộ manifest trước. Nếu digest đó không có hoặc không khớp, đặc tả cho phép kiểm tra theo main attributes và từng section. Điều này hỗ trợ tình huống manifest được **bổ sung section mới** sau lần ký trước: chữ ký cũ vẫn có thể hợp lệ cho các entry ban đầu, miễn các section và byte đã ký không thay đổi. Không được suy diễn rằng phần bổ sung cũng được signer cũ bảo vệ.

## 5. Signature block và chuỗi chứng thư người ký

Tệp `META-INF/<tên>.RSA`/`.EC`/`.DSA` là signature block, thường ở dạng PKCS #7/CMS SignedData. Nó chứa chữ ký số của `.SF`, cùng chứng thư X.509 phục vụ xác minh người ký; không phải nơi lưu trữ private key. Tùy thuật toán của khóa và JDK, tên phần mở rộng sẽ khác nhau.

**Chuỗi chứng thư (certificate chain)** thường gồm:

1. **Leaf / signer certificate:** chứng thư đầu cuối chứa public key dùng xác minh chữ ký, chủ thể (Subject) và thời hạn.
2. **Intermediate CA certificate(s):** nếu người ký dùng CA, các chứng thư trung gian nối leaf đến CA cấp trên.
3. **Trust anchor:** gốc tin cậy do bên kiểm tra lựa chọn trong truststore/chính sách. Root không bắt buộc phải được nhúng vào JAR và việc xuất hiện trong JAR cũng không tự khiến nó đáng tin.

Chuỗi được xây dựng và đánh giá theo chính sách PKIX/X.509: chữ ký giữa các chứng thư, thời hạn, KeyUsage/ExtendedKeyUsage (nếu có), thuật toán được phép, trạng thái thu hồi khi yêu cầu, và trust anchor được chấp nhận. Chuỗi chứng thư **không thay thế** kiểm tra digest của entry; hai bước giải quyết hai vấn đề khác nhau.

Một JAR có thể được ký đúng bằng self-signed certificate. Khi đó kiểm tra chữ ký có thể thành công nhưng công cụ vẫn cảnh báo `self-signed certificate` hoặc `certificate chain not validated`. Đối với triển khai thực tế, chính sách phải xác định người ký nào được tin cậy; không tin chỉ vì certificate xuất hiện trong signature block.

**Timestamp (dấu thời gian):** nếu `jarsigner` dùng dịch vụ TSA, thông tin timestamp đã ký có thể được đính kèm; verifier kiểm tra chữ ký/chuỗi của TSA theo chính sách riêng. Timestamp tin cậy giúp chứng minh thời điểm ký nằm trong giai đoạn chứng thư người ký hợp lệ. Timestamp không giúp bỏ qua kiểm tra integrity và không sửa được một entry đã bị thay đổi.

## 6. Trình tự xác minh và điểm phát hiện sai lệch

Dưới góc nhìn người xác minh:

1. Mở JAR với chế độ verification. Xác minh chữ ký cryptographic trên `.SF` bằng public key trong certificate signer của signature block.
2. Xác minh nội dung liên quan trong manifest qua digest của `.SF`: toàn manifest hoặc main attributes/section theo quy tắc đặc tả.
3. Khi đọc **đến hết nội dung từng entry**, tính digest từ byte thực và đối chiếu digest ở section manifest được bảo vệ. Sai lệch có thể phát sinh `SecurityException`.
4. Xác định entry đó có bao nhiêu người ký và lấy chuỗi chứng thư của từng người ký.
5. Thực hiện kiểm tra **tin cậy/policy** riêng: người ký được cho phép không, chain có tới trust anchor mong đợi không, certificate, thuật toán, timestamp và các quy tắc doanh nghiệp có đạt không.
6. Kiểm kê **tất cả entry bắt buộc phải ký**. Sự thành công của một entry đã ký không đồng nghĩa các entry khác cũng được ký.

Tình huống thường gặp:

| Thay đổi hoặc trạng thái | Kết quả phải hiểu đúng |
| --- | --- |
| Sửa byte của `Hello.class` sau ký | Digest thực không còn khớp manifest đã ký; xác minh entry thất bại |
| Sửa `.SF` nhưng giữ signature block cũ | Chữ ký trên `.SF` không khớp |
| Chỉ thêm resource mới sau khi ký | Entry mới có thể **unsigned**; entry ban đầu vẫn có thể hợp lệ |
| Certificate tự ký, chưa được tin cậy | Integrity/signature có thể hợp lệ nhưng identity/trust chưa đạt |
| Certificate hết hạn hoặc bị thu hồi | Cần xét policy, thời điểm ký và timestamp tin cậy nếu có |
| Algorithm ký/digest nằm trong danh sách bị vô hiệu hóa | JDK có thể coi JAR như unsigned hoặc từ chối theo chính sách thuật toán |

Việc **repackaging, shading, re-compression, sửa manifest hoặc ghi lại JAR** sau ký phải được xem là thay đổi cần kiểm tra lại. Quy trình an toàn thường là **build hoàn tất → ký → verify → phát hành bất biến**.

## 7. Thực hành: tạo, ký và kiểm tra JAR trên JDK 17+

Các lệnh dưới đây chạy trong thư mục thực hành có JDK 17+ và `java`, `javac`, `jar`, `keytool`, `jarsigner` trên `PATH`. Chứng thư được tạo **chỉ để học tập**, không dùng làm chứng thư phát hành thật.

Tạo tệp **Hello.java**:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Signed JAR demo");
    }
}
~~~

Biên dịch, đóng gói JAR chưa ký và chạy thử:

~~~bash
javac Hello.java
jar --create --file unsigned.jar Hello.class
java -cp unsigned.jar Hello
~~~

Stdout chính xác:

~~~text
Signed JAR demo
~~~

Tạo một cặp khóa RSA và chứng thư X.509 tự ký trong PKCS#12; `keytool` sẽ hỏi mật khẩu keystore qua terminal:

~~~bash
keytool -genkeypair -alias jar-demo -keyalg RSA -keysize 3072 -validity 90 -storetype PKCS12 -keystore demo.p12 -dname "CN=Training Signer, OU=Learning, O=Example, C=VN"
~~~

Dùng alias `jar-demo` để ký và xuất thành **signed.jar**, giữ nguyên **unsigned.jar**:

~~~bash
jarsigner -keystore demo.p12 -storetype PKCS12 -signedjar signed.jar unsigned.jar jar-demo
~~~

Công cụ sẽ hỏi mật khẩu. Đọc cấu trúc JAR và kiểm tra chữ ký:

~~~bash
jar --list --file signed.jar
jarsigner -verify -verbose -certs signed.jar
java -cp signed.jar Hello
~~~

Lệnh `jar --list` sẽ cho thấy `META-INF/MANIFEST.MF`, cặp tệp signature `META-INF/JAR-DEMO.SF` và `META-INF/JAR-DEMO.RSA`, cùng `Hello.class`. Tên và thứ tự entry hiển thị có thể thay đổi theo công cụ. Lệnh `java` cuối vẫn in đúng `Signed JAR demo` như trước.

Trong kết quả `jarsigner -verify -verbose -certs`, ký hiệu `s` cho biết chữ ký entry được xác minh, `m` cho biết entry có trong manifest; `k` liên quan việc tìm thấy chứng thư trong keystore đang dùng. Hãy kiểm tra **từng entry ứng dụng** và phần cảnh báo của công cụ. Vì bài demo dùng self-signed certificate và không có TSA, có thể thấy cảnh báo về chuỗi chứng thư và timestamp; đó là dự kiến, không phải dấu hiệu byte `Hello.class` đã bị sửa.

Trong CI/CD phát hành thực tế, có thể dùng `jarsigner -verify -strict -verbose -certs signed.jar` để biến một số **severe warnings** thành mã thoát khác 0. Lưu ý lệnh `-strict` đối với certificate tự ký của bài demo có thể thất bại đúng theo thiết kế. `-strict` không thay chính sách kiểm kê entry và tin cậy publisher của tổ chức.

## 8. Kiểm tra từng entry bằng API Java 17

`JarFile` có chế độ `verify=true` để kiểm tra tính toàn vẹn/chữ ký của nội dung entry khi đọc. `JarEntry.getCodeSigners()` hoặc `getCertificates()` chỉ có thông tin đáng tin cậy sau khi **đọc hết stream của entry**; hỏi trước thường trả về `null`. API này **không tự đánh giá mức tin cậy của certificate signer**.

Chương trình sau liệt kê người ký của các entry ứng dụng. Để ví dụ ngắn gọn, nó bỏ qua `META-INF/`; khi triển khai kiểm kê nghiêm ngặt phải xem cả các resource không thuộc signature metadata trong thư mục đó.

Tạo **InspectJar.java**:

~~~java
import java.io.OutputStream;
import java.security.CodeSigner;
import java.security.cert.X509Certificate;
import java.util.Enumeration;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

public class InspectJar {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: java InspectJar jar-file");
        }

        int signedEntries = 0;
        int unsignedEntries = 0;

        try (JarFile jar = new JarFile(args[0], true)) {
            Enumeration<JarEntry> entries = jar.entries();

            while (entries.hasMoreElements()) {
                JarEntry entry = entries.nextElement();
                if (entry.isDirectory() || entry.getName().startsWith("META-INF/")) {
                    continue;
                }

                // Đọc đến EOF mới hoàn tất kiểm tra digest/chữ ký cho entry.
                try (var input = jar.getInputStream(entry)) {
                    input.transferTo(OutputStream.nullOutputStream());
                }

                CodeSigner[] signers = entry.getCodeSigners();
                int count = signers == null ? 0 : signers.length;
                System.out.printf("%s | signers=%d%n", entry.getName(), count);

                if (count == 0) {
                    unsignedEntries++;
                    continue;
                }

                signedEntries++;
                for (CodeSigner signer : signers) {
                    var chain = signer.getSignerCertPath().getCertificates();
                    System.out.println("  certificate chain length: " + chain.size());
                    if (!chain.isEmpty() && chain.get(0) instanceof X509Certificate leaf) {
                        System.out.println("  signer subject: " + leaf.getSubjectX500Principal());
                    }
                    System.out.println("  has timestamp: " + (signer.getTimestamp() != null));
                }
            }
        }

        System.out.printf("Signed entries: %d, unsigned entries: %d%n",
                signedEntries, unsignedEntries);
    }
}
~~~

Chạy:

~~~bash
javac InspectJar.java
java InspectJar signed.jar
~~~

Với JAR nhỏ đã ký ở mục 7, chương trình sẽ nhận diện `Hello.class` có một signer; phần cuối:

~~~text
Signed entries: 1, unsigned entries: 0
~~~

Các dòng subject và độ dài certificate chain phụ thuộc certificate thực tế. Nếu entry được ký bị thay byte, chương trình có thể ném `SecurityException` trong lúc đọc hoặc xác minh. Nếu entry không được ký, `getCodeSigners()` trả về `null` dù chương trình đã đọc hết nó. `CodeSigner.getSignerCertPath()` cho chuỗi chứng thư của từng signer; `getTimestamp()` có thể `null` nếu ký không có timestamp.

**Giới hạn quan trọng:** chương trình minh họa chỉ kiểm tra chữ ký/digest và đếm signer. Để quyết định có **chấp nhận** publisher hay không, ứng dụng cần truststore/PKIX validation, danh sách signer được phép, chính sách thuật toán và timestamp. Đừng lấy `count > 0` làm quy tắc tin cậy trong môi trường thật.

## 9. Cách đọc kết quả đúng và kiểm thử âm tính

Cần phân biệt ba kết luận riêng biệt thay vì chỉ nhìn dòng `jar verified`:

1. **Byte của các entry được ký có khớp?** Kiểm tra phần xác minh chữ ký và digest; mọi entry bắt buộc ký phải được đọc/kiểm tra.
2. **Mọi entry quan trọng đều đã ký?** Kiểm kê file ứng dụng/resource được phép. Entry thêm sau khi ký có thể unsigned mà chữ ký trên entry cũ vẫn đúng.
3. **Người ký có được chấp nhận?** Xem chain, certificate validity/usage, trust anchor, revocation/timestamp và chính sách tổ chức.

Một bộ thử nghiệm nên có:

- **Mẫu chuẩn:** JAR ký, mọi entry cần bảo vệ có signer theo dự kiến.
- **Sửa nội dung entry:** dựng bản thử nghiệm bằng cách thay byte rồi kiểm tra lại; phải bắt được lỗi integrity.
- **Thêm entry chưa ký:** kiểm tra rằng quy trình phát hành phát hiện entry ngoài danh sách đã ký.
- **Self-signed/unknown CA:** crypto verification có thể hợp lệ, nhưng trust phải bị từ chối bởi policy thật.
- **Expired/disabled algorithm:** xem cảnh báo và mã thoát của `jarsigner -strict`, đối chiếu chính sách JDK đang chạy.
- **Nhiều người ký:** xác minh signer theo **entry**, không chỉ đếm tệp `.SF` toàn JAR.

Không cần phá khóa riêng để giả mạo một JAR: một attacker có thể thử chèn entry unsigned, đổi classpath, thay dependency, hoặc lợi dụng code loader bỏ qua bước kiểm tra policy. Vì vậy phát hành JAR an toàn còn cần khóa phiên bản dependency, kiểm tra provenance, giới hạn nguồn tải và không thực thi trực tiếp gói chưa được tin cậy.

## 10. Lỗi phổ biến và cách tránh

| Nhầm lẫn | Diễn giải/cách sửa |
| --- | --- |
| “Manifest là chữ ký số.” | Manifest chỉ chứa metadata và digest. Chữ ký cryptographic nằm trong signature block của `.SF`. |
| “SHA-256-Digest trong `.SF` là hash của file `.class`.” | Digest trong `.SF` trỏ tới **section manifest**; digest trong manifest trỏ tới **byte entry**. |
| “Có `META-INF/*.RSA` thì mọi file đều được ký.” | Có thể có entry unsigned; phải xem signer theo entry và chính sách phạm vi. |
| “`jarsigner -verify` thành công tức là publisher đáng tin.” | Chữ ký hợp lệ và certificate chain được tin cậy là hai kết luận tách biệt. |
| “Gọi `getCodeSigners()` ngay sau `getJarEntry()`.” | Phải đọc hết input stream với verification bật rồi mới lấy signer. |
| “Có certificate trong block nên root CA đương nhiên trusted.” | Trust anchor do phía verifier cấu hình; root được nhúng không tạo niềm tin. |
| “Sửa tên, nén lại hoặc chèn resource sau ký không sao.” | Luôn kiểm tra lại; các thay đổi có thể làm invalid signature hoặc sinh entry unsigned. |
| “Dùng chứng thư tự ký demo để publish production.” | Cần quy trình cấp phát/giữ private key, certificate code signing và chính sách tin cậy thật. |
| “Không có TSA thì chữ ký vô giá trị ngay.” | Chữ ký vẫn có thể xác minh; thiếu timestamp làm việc đánh giá hợp lệ theo thời gian khó hơn và có thể gây cảnh báo. |

## 11. Checklist triển khai

- Build artifact cuối cùng xong trước khi ký; lưu artifact đã ký bất biến.
- Dùng thuật toán hiện đại được JDK và chính sách của hệ thống chấp nhận; tránh SHA-1/MD5 và các thuật toán bị vô hiệu hóa.
- Bảo vệ private key bằng keystore/secret manager/HSM phù hợp; không hard-code mật khẩu trong mã hay log.
- Chọn signer certificate và chain đúng mục đích code signing; xác định trust anchor trước khi phát hành.
- Cân nhắc TSA đáng tin cậy, kiểm tra tính hợp lệ của TSA và kế hoạch xử lý hết hạn/thu hồi.
- Chạy `jarsigner -verify -verbose -certs` và `-strict` theo policy với certificate thật; đọc cảnh báo và exit code.
- Bảo đảm **mọi entry bắt buộc** có signer đúng; không chấp nhận resource unsigned bất ngờ.
- Với classloader tùy biến hoặc công cụ tự kiểm tra, đọc hết entry trước khi dùng `getCodeSigners()`; áp dụng kiểm tra trust riêng.
- Nếu thay đổi JAR sau ký, build/ký/verify lại và kiểm thử đường dẫn triển khai cuối cùng.

## 12. Câu hỏi tự kiểm tra

**1. Nếu thay `Hello.class` nhưng giữ nguyên manifest và `.SF` thì sao?** Verifier tính digest từ byte `Hello.class` mới; digest không khớp giá trị đã ký trong manifest nên thất bại khi xác minh entry.

**2. Vì sao `.SF` cần digest của section manifest?** Vì chữ ký số ký `.SF`, còn manifest chứa digest của byte entry. Digest section tạo cầu nối được bảo vệ giữa `.SF` và manifest.

**3. Tại sao certificate self-signed vẫn có thể xác minh chữ ký?** Public key của certificate xác minh được phép toán chữ ký, nhưng certificate tự ký không tự trở thành trust anchor của người kiểm tra.

**4. Vì sao `getCodeSigners()` có thể trả `null`?** Entry unsigned hoặc chưa được đọc/verify đến EOF; cũng phải kiểm tra chế độ verify và lỗi thuật toán/chữ ký.

**5. Nếu JAR được thêm file sau lần ký ban đầu, chứng thư người ký cũ đảm bảo file mới không?** Không. Cần kiểm tra phạm vi signer của chính file mới; chữ ký cũ chỉ có thể tiếp tục bảo vệ phần đã ký trước.

## Tài liệu chuẩn để đối chiếu

- JAR File Specification (Java 17), phần Signed JAR File và Signature Validation: https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html
- `jarsigner` tool: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html
- `java.util.jar.JarFile` (Java 17): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html
- `java.util.jar.JarEntry` (Java 17): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarEntry.html
