# 12.7 KeyStore.Builder, LoadStoreParameter và bảo vệ mật khẩu trong ứng dụng

Ứng dụng Java có thể cần mở private key để ký số, secret key để mã hóa dữ liệu, hoặc certificate tin cậy để xác minh đối tác. **KeyStore** là API thống nhất cho việc chứa và truy cập các loại entry này, nhưng bản thân API không tự giải quyết toàn bộ bài toán **lấy mật khẩu từ đâu, thời điểm mở khóa, vòng đời bí mật trong RAM, quyền truy cập file/token và thay đổi khóa khi ứng dụng đang chạy**.

Bài học tập trung vào ba thành phần:

1. **KeyStore.Builder**: mô tả cách khởi tạo và cung cấp protection cho entry, có thể trì hoãn tải kho đến lúc cần.
2. **KeyStore.LoadStoreParameter**: giao diện mô tả tham số cho **KeyStore.load(...)** và **KeyStore.store(...)**; provider/loại kho quyết định cách diễn giải.
3. **KeyStore.ProtectionParameter**, nhất là **PasswordProtection** và **CallbackHandlerProtection**: cung cấp mật khẩu hoặc cơ chế hỏi mật khẩu.

Sau bài, bạn có thể phân biệt password bảo vệ **file/keystore** và **entry**, chọn overload đúng, xây dựng hai ví dụ Java 17+ chạy được, xử lý sai password, dọn char[]/protection đúng vòng đời, và thiết kế service không làm lộ private key hay password qua log/cấu hình.

## 1. Nền tảng cần nhớ khi dùng Builder

`KeyStore` quản lý các entry theo alias; ba loại chính là **PrivateKeyEntry** (private key kèm certificate chain), **SecretKeyEntry** (khóa đối xứng) và **TrustedCertificateEntry** (chứng chỉ công khai được cấu hình làm nguồn tin cậy). Một keystore dùng làm **identity store** khác với một **truststore** ở *vai trò tiêu thụ*; bản thân PKCS12 có thể được dùng cho cả hai.

Bài này tập trung **cách ứng dụng nạp kho và cấp secret theo thời điểm**, chứ không phân loại lại mọi entry: `Builder` quản lý nguồn/lifecycle, `LoadStoreParameter` truyền điều kiện load/store cho provider, còn `PasswordProtection` và `CallbackHandlerProtection` cung cấp thông tin bảo vệ. Với PKCS11/HSM, entry có thể được truy cập qua handle và PIN thay vì key exportable trong file.

**Giới hạn cần giữ rõ:** alias không phải quyền truy cập; password mở kho có thể khác password mở từng entry; builder không tự biến file PKCS12 thành secret manager, cũng không tự kiểm tra certificate chain hay quyền ký.

## 2. Vòng đời cơ bản của KeyStore

~~~text
KeyStore.getInstance("PKCS12")  -> đối tượng chưa load
        |
        v
KeyStore.load(...)  -> đọc file hoặc khởi tạo theo provider
        |
   lỗi / thành công
        |
        v
KeyStore.getEntry(alias, protection)
        |
        v
key/certificate để dùng cho nghiệp vụ
        |
        v
KeyStore.store(...) nếu có thay đổi cần ghi lại
~~~

Cách truyền thống trong một method có đủ import và các biến Path/char[]:

~~~java
KeyStore ks = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(path)) {
    ks.load(in, password);
}
KeyStore.Entry entry = ks.getEntry(
        "service-key", new KeyStore.PasswordProtection(password));
~~~

**Đây là mảnh code minh họa**, không phải chương trình đầy đủ. Khi tạo mới một kho rỗng, có thể dùng **ks.load(null, password)** với implementation phù hợp; để mở **kho đã tồn tại**, phải thật sự cung cấp file/stream hoặc cấu hình provider. **KeyStore.getInstance("PKCS12") không tự đọc file**. Sau khi đọc entry, phải bảo vệ key và quyền sử dụng, không chỉ bảo vệ password mở file.

## 3. KeyStore.Builder: cấu hình nguồn kho và trì hoãn load

**KeyStore.Builder** là abstract nested class, tạo qua các static factory **newInstance**. Builder giữ thông tin để instantiate/load KeyStore và cung cấp protection cho entry. Nó hữu ích khi chưa muốn mở hết mọi file, chưa muốn hỏi password sớm hoặc framework cần danh sách các nguồn khóa.

| Factory | Vai trò | Điều cần chú ý |
| --- | --- | --- |
| **newInstance(KeyStore, ProtectionParameter)** | Bọc KeyStore đã khởi tạo cùng protection. | Nếu KeyStore chưa được load thì không hợp lệ; getKeyStore trả lại object được bọc. |
| **newInstance(String type, Provider, File, ProtectionParameter)** | Mô tả KeyStore của **file hiện có**. | Lần getKeyStore đầu mới mở/load; các lần sau trả cùng instance. |
| **newInstance(File, ProtectionParameter)** | Tự dò loại kho từ file (Java 9+). | File phải hợp lệ; kiểm thử khả năng nhận dạng. |
| **newInstance(String type, Provider, ProtectionParameter)** | Tạo KeyStore type cụ thể, load bằng LoadStoreParameter chứa protection. | Mỗi getKeyStore tạo object mới theo API; provider phải hỗ trợ kiểu tham số. |

Tham số **Provider provider = null** nghĩa dùng lựa chọn provider của JCA, không có nghĩa là không bảo vệ khóa. Pin provider trong yêu cầu HSM/FIPS hoặc tương thích cụ thể, nhưng phải kiểm tra độ di động khi triển khai.

### 3.1. Builder file-based có lazy loading và cache instance

~~~text
Builder.newInstance("PKCS12", null, existingFile, protection)
                  |
                  | Chưa gọi load
                  v
           builder.getKeyStore()
                  |
              load file lần đầu
                  |
                  v
           KeyStore đã initialized
                  |
       +----------+----------------------+
       |                                 |
builder.getKeyStore()               builder.getProtectionParameter(alias)
lần sau: cùng KeyStore               sau getKeyStore mới hợp lệ
~~~

Theo contract của Java 17:

- File-based Builder **getKeyStore() lần đầu** tạo/load; **những lần sau trả cùng đối tượng**. Nếu lần đầu thất bại bằng KeyStoreException thì các lần sau cũng báo lỗi, không tự thử lại.
- **getProtectionParameter(alias)** phải gọi **sau getKeyStore()**; nếu không có thể nhận IllegalStateException.
- File-based Builder trả **PasswordProtection** chứa mật khẩu dùng khi load file. Nó **không tự biết mật khẩu khác** được dùng để bảo vệ một entry cụ thể.
- Nếu một entry có password riêng khác password file, việc **getEntry** có thể cần PasswordProtection khác đúng entry hoặc cơ chế chuyên biệt tùy provider.
- Một Builder đã load **không tự hot reload file** khi file/secret thay đổi. Muốn rotation, tổ chức lại vòng đời đối tượng và tạo builder mới.
- Builder **không làm KeyStore mutable thread-safe** để đồng thời thêm/xóa entry hoặc store.

### 3.2. Chọn Builder hay load trực tiếp?

**Dùng Builder** khi framework nhận một tập nguồn khóa, khi lazy loading giúp giảm nhu cầu password sớm, hoặc khi callback/provider khác nhau. **Dùng KeyStore.getInstance + load(InputStream,char[])** khi ứng dụng chỉ mở một file một lần lúc startup và không cần abstraction Builder. Cả hai đều là API hợp lệ; chọn cách đơn giản đáp ứng ownership, provider và lifecycle.

## 4. Bảo vệ entry: ProtectionParameter và PasswordProtection

**KeyStore.ProtectionParameter** mô tả cơ chế mở/bảo vệ entry, và một số API dùng nó khi load/store. Loại phổ biến là **KeyStore.PasswordProtection**, nhận **char[]**.

Trong method có nguồn password tin cậy:

~~~java
char[] password = readSecretFromTrustedSource();
KeyStore.PasswordProtection protection =
        new KeyStore.PasswordProtection(password);
try {
    // Dùng protection để load keystore hoặc lấy entry.
} finally {
    protection.destroy();
    Arrays.fill(password, '\0');
}
~~~

**Mảnh code này không độc lập** vì readSecretFromTrustedSource là trách nhiệm của ứng dụng; hai chương trình bên dưới hoàn toàn runnable và minh họa vòng đời bằng password test.

### 4.1. Constructor clone char[] và vì sao cần destroy()

Java 17 **PasswordProtection(char[])** **clone** mảng password đầu vào. Điều này có hai hệ quả:

1. Xóa mảng **password của caller** bằng Arrays.fill không tự xóa **bản sao** bên trong PasswordProtection.
2. **PasswordProtection.destroy()** xóa password nội bộ; **isDestroyed()** kiểm tra trạng thái và **getPassword() sau destroy** phát sinh IllegalStateException.

Ngược lại, **getPassword() trả tham chiếu tới mảng bên trong**, không phải một bản sao an toàn để phát tán. Không thay đổi mảng trả về tùy tiện; không cho thread khác truy cập; hủy object khi chắc chắn builder/getEntry/provider không còn dùng nó.

**new PasswordProtection(password, protectionAlgorithm, protectionParameters)** có thể chỉ định thuật toán/params để bảo vệ entry ở provider hỗ trợ. Không tự cho rằng mọi KeyStore type hỗ trợ mọi thuật toán bảo vệ theo tên; cần kiểm thử.

### 4.2. Mật khẩu file và mật khẩu entry không đồng nghĩa

Một sơ đồ có thể dùng cùng mật khẩu khi tạo file và setEntry, như ví dụ runnable để đơn giản hóa. Trong production, có thể có:

~~~text
Keystore:
  storePassword ---> bảo vệ/kiểm tra integrity file
  alias A -------> entryPasswordA ---> private key A
  alias B -------> entryPasswordB ---> private key B
~~~

Tuy nhiên **không phải provider nào cũng cho dùng password riêng từng entry**. Khi chạy Builder file-based, **builder.getProtectionParameter(alias)** trả protection gắn với password đã dùng load file, không tự lấy password riêng A/B. Nếu cần tách, dùng **getEntry(alias, new PasswordProtection(entryPassword))** với provider có hỗ trợ, hoặc triển khai strategy nhập PIN/password theo provider.

### 4.3. PasswordProtection không phải password hashing

Password của keystore dùng làm **protection secret** cho dữ liệu/entry; nó không phải cùng một thứ với **password verifier cho người dùng đăng nhập**. Không đem PBKDF2 output của password người dùng dùng như secret keystore tùy tiện; không dùng keystore để lưu database password plaintext. Các profile PKCS12 có thể dùng password-based encryption/MAC theo định dạng và provider; muốn biết thuật toán/cost cụ thể phải kiểm tra implementation/cấu hình của môi trường.

## 5. CallbackHandlerProtection: yêu cầu mật khẩu khi cần

**KeyStore.CallbackHandlerProtection** giữ một **javax.security.auth.callback.CallbackHandler**. File-based Builder có thể gọi handler với **PasswordCallback** khi thực sự cần mật khẩu để mở kho. Đây là cách trì hoãn việc lấy secret cho tới lúc load, hữu ích khi secret nằm trong một nguồn được quản lý hoặc có tương tác với người vận hành.

~~~text
Builder.newInstance(file, new CallbackHandlerProtection(handler))
                        |
                getKeyStore lần đầu
                        |
                 handler.handle(...)
                        |
             PasswordCallback.setPassword(...)
                        |
                  KeyStore.load
~~~

**Điều quan trọng:**

- Callback không biến password thành “không cần giữ trong RAM”; lúc sử dụng, secret vẫn đi qua buffer trong process.
- Handler cần xử lý đúng loại callback, hủy mảng tạm sau khi truyền cho PasswordCallback (API setPassword sao chép dữ liệu), và xử lý cancellation/timeout.
- Nếu provider yêu cầu loại callback khác, phải kiểm tra khả năng hỗ trợ thay vì luôn cast sang PasswordCallback.
- Không dùng System.console() trực tiếp trong request handler của web server chạy không tương tác; cần kiến trúc secret source có quyền, giới hạn truy cập và audit phù hợp.
- Không lưu password dài hạn trong lambda/field singleton nếu có thể tránh. Handler chỉ nên lấy secret khi cần và xóa bản sao khi hoàn thành.
- File-based Builder API chấp nhận **PasswordProtection hoặc CallbackHandlerProtection**; các implementation ProtectionParameter khác có thể bị IllegalArgumentException.
- Việc cấp password hoặc PIN của HSM không đồng nghĩa khóa private có thể được xuất. Key handle và chính sách usage của token vẫn có hiệu lực.

Một snippet dùng CallbackHandler trong method đã nhận một **Supplier<char[]> secretSupplier** đáng tin; đây là mảnh code minh họa chứ không phải chương trình độc lập:

~~~java
CallbackHandler handler = callbacks -> {
    for (Callback cb : callbacks) {
        if (!(cb instanceof PasswordCallback pc)) {
            throw new UnsupportedCallbackException(cb);
        }
        char[] supplied = secretSupplier.get();
        try {
            pc.setPassword(supplied);
        } finally {
            Arrays.fill(supplied, '\0');
        }
    }
};
KeyStore.ProtectionParameter param =
        new KeyStore.CallbackHandlerProtection(handler);
~~~

Các import liên quan thuộc javax.security.auth.callback.*, java.security.KeyStore, java.util.Arrays và java.util.function.Supplier. **Supplier được ứng dụng cài từ nguồn secret phù hợp**. PasswordCallback còn phải được clear đúng thời điểm bởi thành phần quản lý callback/provider; không giả định đoạn minh họa đã xóa hết bản sao mọi nơi.

## 6. LoadStoreParameter: trừu tượng hóa thông số load và store

**KeyStore.LoadStoreParameter** là interface nested của KeyStore, có một method:

~~~java
KeyStore.ProtectionParameter getProtectionParameter();
~~~

Nó có thể được triển khai bằng một anonymous class/lambda cho Java 17:

~~~java
KeyStore.PasswordProtection protection =
        new KeyStore.PasswordProtection(password);
KeyStore.LoadStoreParameter parameters = () -> protection;
~~~

**Mảnh code này nằm trong method có char[] password đã khai báo**, không phải main độc lập. **LoadStoreParameter không phải file path, không chứa ciphertext, và không tự cung cấp một chuẩn chung để load bất kỳ định dạng**. Provider đọc tham số và quyết định nó có được hỗ trợ hay không.

### 6.1. Phân biệt overload của KeyStore

| API | Nguồn dữ liệu | Dùng khi nào | Bẫy thường gặp |
| --- | --- | --- | --- |
| **load(InputStream, char[])** | Dữ liệu lấy từ stream (null để khởi tạo mới) | File-based JKS/PKCS12 phổ biến | Cần đóng stream; password không tự được xóa. |
| **load(LoadStoreParameter)** | Theo provider + protection parameter | Provider hiểu cách tải dữ liệu, có thể là token hoặc khởi tạo mới | **Không có InputStream trong interface**, không giả định tự mở file. |
| **store(OutputStream, char[])** | Ghi bytes vào stream | File-based keystore, xuất bản ghi mới | Cần quản lý ghi file an toàn và quyền đọc, không chỉ gọi store. |
| **store(LoadStoreParameter)** | Theo provider + param | Token/provider có cơ chế lưu riêng | Có thể ném IllegalArgumentException/UnsupportedOperationException nếu provider không hỗ trợ. |
| **KeyStore.Builder.newInstance(type, provider, protection)** | Tạo KeyStore và gọi load với LoadStoreParameter bọc protection | Khi lifecycle do provider quản lý | Đọc contract: mỗi getKeyStore tạo mới cho overload này, khác file Builder. |

**Cảnh báo:** gọi **load(parameters)** với một LoadStoreParameter do bạn tự tạo **không có nghĩa PKCS12 tự tìm file**. Nếu chỉ có password protection, thiếu đường dẫn file là bình thường. Tùy provider, điều này có thể dùng để khởi tạo kho rỗng hoặc mở token; muốn đọc file cụ thể, dùng load(InputStream, char[]) hoặc file Builder phù hợp.

### 6.2. LoadStoreParameter khác ProtectionParameter thế nào?

~~~text
ProtectionParameter = thông tin/phương pháp bảo vệ
                    PasswordProtection / CallbackHandlerProtection / provider-specific

LoadStoreParameter = một container/contract dành cho load/store,
                     có method getProtectionParameter()

KeyStore.load(parameters) -> provider diễn giải container đó
KeyStore.getEntry(alias, protection) -> protection của entry cụ thể
~~~

Không thay hai interface cho nhau trong method signature. Builder file-based nhận **ProtectionParameter**, trong khi **KeyStore.load(param)** yêu cầu **LoadStoreParameter**. Một số provider có LoadStoreParameter chuyên dụng (ví dụ **DomainLoadStoreParameter** phục vụ cấu hình domain), và không phải mọi implementation đều chấp nhận một lambda chứa PasswordProtection.

### 6.3. Nên dùng khi nào?

- Provider keystore cần PIN/mật khẩu hoặc cấu hình load/store không thể diễn tả bằng InputStream.
- Hệ thống dùng token/hardware hoặc nhiều keystore có định nghĩa domain/provider-specific.
- Framework muốn một abstraction chung cho khởi tạo kho với protection, nhưng vẫn phải kiểm tra support.
- Trong file PKCS12 đơn giản, **load(InputStream,char[])** và **store(OutputStream,char[])** thường rõ ràng, dễ debug hơn.

**Đừng bắt UnsupportedOperationException rồi tự chuyển sang lưu plain text/key bytes**. Phải chọn đúng provider/method và chính sách bảo vệ.

## 7. Java 17+ — Demo 1: KeyStore.Builder mở PKCS12 và đọc SecretKeyEntry

Chương trình sau là ví dụ **độc lập**, tạo một keystore PKCS12 tạm chứa khóa AES 128 bit, lưu vào file, sau đó dùng **Builder.newInstance(type, null, file, PasswordProtection)** để load. Nó kiểm tra alias, nội dung SecretKey, việc file Builder cache instance và sai password.

Tạo file **BuilderKeyStoreDemo.java**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.OutputStream;
import java.security.KeyStore;
import java.security.KeyStoreException;
import java.security.MessageDigest;
import java.util.Arrays;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public class BuilderKeyStoreDemo {
    public static void main(String[] args) throws Exception {
        char[] storePassword = "demo-password-not-for-production".toCharArray();
        char[] wrongPassword = "wrong-password".toCharArray();
        Path tempFile = Files.createTempFile("builder-demo-", ".p12");
        KeyStore.PasswordProtection writeProtection = null;
        KeyStore.PasswordProtection builderProtection = null;
        KeyStore.PasswordProtection entryProtection = null;
        try {
            KeyStore created = KeyStore.getInstance("PKCS12");
            created.load(null, storePassword);

            KeyGenerator generator = KeyGenerator.getInstance("AES");
            generator.init(128);
            SecretKey aesKey = generator.generateKey();

            writeProtection = new KeyStore.PasswordProtection(storePassword);
            created.setEntry("service-aes",
                    new KeyStore.SecretKeyEntry(aesKey), writeProtection);
            try (OutputStream out = Files.newOutputStream(tempFile)) {
                created.store(out, storePassword);
            }

            builderProtection = new KeyStore.PasswordProtection(storePassword);
            KeyStore.Builder builder = KeyStore.Builder.newInstance(
                    "PKCS12", null, tempFile.toFile(), builderProtection);
            KeyStore loaded = builder.getKeyStore();
            entryProtection = (KeyStore.PasswordProtection)
                    builder.getProtectionParameter("service-aes");
            KeyStore.SecretKeyEntry restored = (KeyStore.SecretKeyEntry)
                    loaded.getEntry("service-aes", entryProtection);

            System.out.println("Alias tồn tại: " +
                    loaded.containsAlias("service-aes"));
            System.out.println("Khóa khôi phục đúng: " +
                    MessageDigest.isEqual(aesKey.getEncoded(),
                            restored.getSecretKey().getEncoded()));
            System.out.println("File Builder cache cùng KeyStore: " +
                    (loaded == builder.getKeyStore()));

            KeyStore.PasswordProtection wrongProtection =
                    new KeyStore.PasswordProtection(wrongPassword);
            try {
                KeyStore.Builder wrongBuilder = KeyStore.Builder.newInstance(
                        "PKCS12", null, tempFile.toFile(), wrongProtection);
                boolean rejected = false;
                try {
                    wrongBuilder.getKeyStore();
                } catch (KeyStoreException expected) {
                    rejected = true;
                }
                System.out.println("Sai mật khẩu bị từ chối: " + rejected);
            } finally {
                wrongProtection.destroy();
            }
        } finally {
            if (entryProtection != null) entryProtection.destroy();
            if (builderProtection != null) builderProtection.destroy();
            if (writeProtection != null) writeProtection.destroy();
            Arrays.fill(storePassword, '\0');
            Arrays.fill(wrongPassword, '\0');
            Files.deleteIfExists(tempFile);
        }
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên (provider hỗ trợ lưu AES SecretKey trong PKCS12):

~~~bash
javac --release 17 -encoding UTF-8 BuilderKeyStoreDemo.java
java BuilderKeyStoreDemo
~~~

Kết quả trên JDK đã kiểm thử:

~~~text
Alias tồn tại: true
Khóa khôi phục đúng: true
File Builder cache cùng KeyStore: true
Sai mật khẩu bị từ chối: true
~~~

### 7.1. Giải thích từng bước

1. **KeyStore.getInstance("PKCS12")** chọn type, **load(null, storePassword)** khởi tạo kho mới.
2. **KeyGenerator.getInstance("AES")** tạo SecretKey test 128 bit; không hardcode key bytes trong ứng dụng.
3. **setEntry("service-aes", SecretKeyEntry, PasswordProtection)** đặt entry vào kho; password entry dùng cùng password file **chỉ để đơn giản hóa demo**.
4. **store(OutputStream, char[])** ghi kho ra file; việc đóng stream được đảm bảo bởi try-with-resources.
5. **Builder.newInstance(..., file, ...)** nhận file đang tồn tại; **getKeyStore** thực hiện tải và kiểm tra password, **getProtectionParameter** được gọi sau khi load.
6. **getEntry** khôi phục entry AES; MessageDigest.isEqual dùng để assert bytes trong bài test; không nên in raw secret key.
7. **getKeyStore hai lần trả cùng object** đúng contract file Builder; code không chứng minh auto reload khi file thay đổi.
8. **Sai password** khi gọi getKeyStore ở builder mới được bắt bằng KeyStoreException; lỗi cần được vận hành phân loại đúng và không log password.
9. **destroy** cho ba đối tượng PasswordProtection và **Arrays.fill** cho hai char[] do demo sở hữu. Cuối cùng xóa file tạm.

**An toàn production:** password literal trong chương trình chỉ dùng để làm demo chạy độc lập. Không copy cách hardcode password vào dự án thật. Temporary file không được xem là vị trí lưu khóa production: file permissions, backup, monitoring, filesystem race và key lifecycle đều cần được quản trị theo hệ thống.

### 7.2. Cần nhớ gì khi đổi alias hoặc password entry?

Alias có thể bị provider chuẩn hóa/case-fold và không nên tạo hai alias chỉ khác chữ hoa/thường. Với file Builder, getProtectionParameter(alias) không biết password riêng cho mỗi alias; nếu một entry cần password độc lập và type/provider cho phép, cấp PasswordProtection phù hợp khi gọi getEntry. Các ứng dụng quy mô lớn nên chuẩn hóa alias và key version, kiểm soát quyền của từng alias trong service thay vì cho client gửi tên alias tùy ý.

## 8. Java 17+ — Demo 2: LoadStoreParameter và PasswordProtection

Ví dụ thứ hai tạo một **LoadStoreParameter** bằng lambda trả về PasswordProtection, truyền cho **KeyStore.load(parameters)**, tạo SecretKeyEntry rồi làm **round-trip** qua **store(OutputStream,char[])** và **load(InputStream,char[])**.

**Phạm vi provider:** trên JDK PKCS12 provider đã kiểm thử, **load(LoadStoreParameter)** với PasswordProtection có thể khởi tạo kho mới rỗng. Đây không phải lời hứa mọi provider/type đều chấp nhận đúng loại parameter; một provider khác có thể từ chối bằng IllegalArgumentException hoặc UnsupportedOperationException. **LoadStoreParameter không mang file path**, nên chương trình dùng ByteArrayOutputStream để chứng minh lưu/đọc bytes theo overload phổ biến.

Tạo file **LoadStoreParameterDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.util.Arrays;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public class LoadStoreParameterDemo {
    public static void main(String[] args) throws Exception {
        char[] password = "demo-only-password".toCharArray();
        KeyStore.PasswordProtection protection =
                new KeyStore.PasswordProtection(password);
        try {
            KeyStore.LoadStoreParameter parameters = () -> protection;
            KeyStore created = KeyStore.getInstance("PKCS12");
            created.load(parameters); // Supported by the tested JDK PKCS12 provider.
            System.out.println("Kho mới trống: " + (created.size() == 0));

            KeyGenerator generator = KeyGenerator.getInstance("AES");
            generator.init(128);
            SecretKey original = generator.generateKey();
            created.setEntry("app-key",
                    new KeyStore.SecretKeyEntry(original), protection);

            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            created.store(bytes, password);

            KeyStore restored = KeyStore.getInstance("PKCS12");
            restored.load(
                    new ByteArrayInputStream(bytes.toByteArray()), password);
            KeyStore.SecretKeyEntry loaded = (KeyStore.SecretKeyEntry)
                    restored.getEntry("app-key", protection);
            System.out.println("Round-trip đúng: " +
                    MessageDigest.isEqual(original.getEncoded(),
                            loaded.getSecretKey().getEncoded()));
            System.out.println("Protection có mật khẩu: " +
                    (parameters.getProtectionParameter() instanceof
                            KeyStore.PasswordProtection));
        } finally {
            protection.destroy();
            Arrays.fill(password, '\0');
        }
        System.out.println("PasswordProtection đã hủy: " +
                protection.isDestroyed());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 LoadStoreParameterDemo.java
java LoadStoreParameterDemo
~~~

Kết quả:

~~~text
Kho mới trống: true
Round-trip đúng: true
Protection có mật khẩu: true
PasswordProtection đã hủy: true
~~~

### 8.1. Quan sát API nào trong ví dụ?

- **LoadStoreParameter parameters = () -> protection** là cách viết ngắn của một implementation interface có method getProtectionParameter().
- **created.load(parameters)** yêu cầu provider diễn giải protection; đoạn này chỉ khởi tạo kho rỗng trong môi trường đã chạy, **không đọc file có sẵn**.
- **store(bytes, password)** dùng overload OutputStream với char[]; **không phải store(LoadStoreParameter)**. Việc provider chấp nhận **load(parameters)** không chứng minh provider đó hỗ trợ **store(parameters)**.
- **restored.load(ByteArrayInputStream, password)** chứng minh dạng PKCS12 byte có thể được đọc lại trên provider đã kiểm thử.
- **getEntry("app-key", protection)** truy xuất SecretKeyEntry; test dùng MessageDigest.isEqual để so sánh bytes và chỉ in true/false.
- **PasswordProtection.destroy()** hủy bản sao password bên trong protection; **Arrays.fill(password, '\0')** hủy mảng caller.
- **ByteArrayOutputStream** trong demo vẫn giữ bytes keystore đã mã hóa/bảo vệ trong RAM và không tự được xóa; ở production cần quản lý buffer, backup và quyền đọc.

### 8.2. Tránh suy diễn từ một test thành công

Test trên cùng JVM/provider với AES SecretKey được tạo bằng KeyGenerator chỉ chứng minh tổ hợp cụ thể đó hoạt động. Đừng khẳng định:

- Mọi PKCS12 provider hỗ trợ SecretKeyEntry hoặc mọi thuật toán secret key.
- Mọi LoadStoreParameter có thể đọc một file được chỉ định bằng password.
- Mọi provider đều dùng cùng password cho store và entry.
- Có thể xuất private key hardware/HSM qua getEncoded().
- File keystore tự an toàn chỉ vì password dài; còn có OS permissions, filesystem policy, backup và key lifecycle.

## 9. Nguồn password trong ứng dụng Java production

Một quyết định kiến trúc quan trọng nằm ở **nơi lấy password và ai được phép dùng nó**.

| Nguồn password | Ưu điểm | Cần cân nhắc |
| --- | --- | --- |
| **Secret manager / Vault / KMS** | Policy truy cập, rotation, audit, cấp secret theo identity workload | Sẵn sàng dịch vụ, cache ngắn hạn, quyền IAM, không log response. |
| **HSM/PKCS11 token** | Private key có thể không rời hardware; PIN/slot/session policy | Đặc thù provider, key handle, PIN, timeout, session pool, khả năng export hạn chế. |
| **Password nhập lúc startup** | Tránh secret cố định trong file config | Không phù hợp headless/auto-scaling nếu không có nhập bí mật an toàn. |
| **File secret mount có ACL hạn chế** | Tích hợp deployment đơn giản | Ownership/ACL/volume/backup/rotation và secret tồn tại trên đĩa. |
| **Environment variable** | Dễ triển khai runtime/container | Có thể lộ qua dump/process introspection, diagnostic, quyền quản trị; không an toàn tuyệt đối. |
| **Source code, Git, CLI arguments, log** | Không có | **Không dùng để lưu/đưa password production** vì dễ lộ qua repository/history/process listing/log. |

**Ưu tiên workload identity + secret manager** hoặc KMS/HSM khi phù hợp. Nếu dùng env var hoặc file mount, vẫn coi là secret cần phân quyền và rotation; không in giá trị để debug.

### 9.1. Vì sao char[] hữu ích nhưng không phải phép màu?

char[] cho caller tự **Arrays.fill** phần bộ nhớ mình sở hữu, khác String bất biến và không thể xóa tại chỗ. Tuy vậy:

- HTTP framework, config parser, callback hoặc provider có thể đã tạo **bản sao** khác.
- PasswordProtection constructor clone char[]; phải **destroy() riêng**.
- getPassword() của PasswordProtection trả tham chiếu nội bộ, nên thành phần khác có thể truy cập khi password còn sống.
- JVM GC, native memory, crash dumps và logging có đặc tính riêng; **không thể bảo đảm xóa sạch mọi bản sao** chỉ bằng Arrays.fill một lần.
- char[] không thay TLS, IAM, entropy password hoặc policy dùng HSM.

Quy tắc: **hạn chế bản sao, thời gian sống và nơi ghi**, dùng finally để clear mảng thuộc sở hữu, destroy protection đúng thời điểm và không lưu password dài hạn trong singleton.

### 9.2. Lifecycle khi dùng Builder

~~~text
SecretSource (phân quyền)
      |
      v
char[] password tạm
      |
      v
PasswordProtection clones char[]
      |
      v
Builder.newInstance(..., protection)
      |
      v
getKeyStore + getEntry (hoàn tất công việc cần secret)
      |
      v
destroy các PasswordProtection đang sở hữu
      |
      v
Arrays.fill mảng caller
      |
      v
Đóng streams, quản lý key handle và file/session
~~~

**Không destroy protection khi Builder còn cần password để load sau này.** Vì Builder có thể lazy-load, phải xác định thời điểm cuối cùng truy cập keystore. Nếu giữ Builder dài hạn, chọn chiến lược secret retrieval/lifecycle tương thích, có thể dùng callback/lazy secret source thay vì tạo PasswordProtection rồi destroy ngay sau cấu hình.

## 10. Load lúc khởi động hay khi có request?

### 10.1. Load lúc startup

Ưu điểm: phát hiện password/file/cert hỏng trước traffic, giảm request latency. Nhược điểm: process cần secret ngay khi khởi động; rotation cần reload đúng.

Workflow:

1. Nhận path, keystore type, alias và key version từ config đáng tin, không từ request trực tiếp.
2. Lấy password từ secret source được phân quyền.
3. Load kho một lần, xác minh alias/type/certificate chain và key usage.
4. Công bố **key handle/service abstraction** sau khi bootstrap thành công.
5. Không log password; xóa buffers khi không cần.
6. Khi rotate, tải **instance mới**, kiểm tra rồi chuyển tham chiếu atomically; giải phóng phiên/handle cũ theo policy.

### 10.2. Lazy load bằng Builder

Ưu điểm: không tải mọi kho sớm, có thể trì hoãn callback. Nhược điểm: lần đầu có I/O, xác thực password hoặc lỗi vận hành đúng lúc request; phải có timeout, monitoring và retry tại lớp điều phối.

Builder **không phải cache secret** và không tự nhận thông báo file thay đổi. Nếu file/password rotate, builder cũ có thể trả **object đã load**; cần xây dựng lại builder/KeyStore hoặc điều phối restart.

### 10.3. Concurrent access

**KeyStore** là container mutable. Nhiều thread cùng setEntry/deleteEntry/store cần được **phối hợp** để tránh lost updates và file không nhất quán. Với keystore chỉ đọc sau bootstrap, xây façade chỉ cung cấp thao tác cần thiết; vẫn phải tôn trọng contract provider/HSM về concurrency và session.

**SecretKey/PrivateKey object** có thể là wrapper/provider handle; không chia sẻ một thao tác mutable đang chạy như Cipher hoặc Signature giữa các thread. KeyStore.Builder không đồng bộ hóa workflow load/rotate/use. Với HSM, có thể cần session pool, timeout và backpressure; retry PIN sai liên tục có thể khóa token.

## 11. Lưu keystore an toàn và quản lý file

File được bảo vệ bằng password vẫn có thể bị sao chép. Cần:

- **File permissions:** hạn chế owner/ACL cho đúng process, không cấp mọi user trên host.
- **Backup:** bản sao được bảo vệ tương đương, có kế hoạch restore và truy xuất password đúng.
- **Atomic update:** ghi file tạm với quyền phù hợp, flush/fsync theo yêu cầu rồi rename atomically nếu filesystem hỗ trợ; nếu crash khi ghi trực tiếp file gốc có thể hỏng kho. Kiểm tra trường hợp rename không atomic và bản sao dự phòng.
- **Key rotation:** chuẩn hóa alias, key ID và phiên bản; không lẫn entry của hai generation.
- **Password rotation:** đổi protection/re-encrypt bằng workflow đúng, kiểm tra kho mới trước khi loại bỏ bản cũ; không phá khả năng đọc dữ liệu lịch sử.
- **Audit:** ghi identity workload, alias, operation và kết quả trong phạm vi an toàn, không log key/password.
- **Environment isolation:** không tái sử dụng password/keys từ dev/test sang production.

Demo 1 dùng **Files.createTempFile** rồi xóa để không chạm file thật; demo 2 dùng **ByteArrayOutputStream** để không ghi cố định. Hai demo không phải quy trình bảo vệ file production hoàn chỉnh.

## 12. Xử lý sai password, sai alias và lỗi provider

Không nên gom mọi lỗi thành một dòng “sai mật khẩu” trong log nội bộ: một vấn đề về file, provider hoặc cấu hình cần cách sửa khác với sai password.

| Tình huống | Kết quả thường thấy | Hướng xử lý |
| --- | --- | --- |
| **File không tồn tại khi tạo file Builder** | IllegalArgumentException ngay tại newInstance(file overload) | Kiểm tra path, quyền và deployment; không tạo file trống giả rồi tiếp tục. |
| **Password file sai** | getKeyStore() của file Builder báo KeyStoreException; load trực tiếp thường IOException, có thể có cause UnrecoverableKeyException | Không retry password sai vô hạn; không log password. |
| **Password entry sai** | getEntry() có thể báo UnrecoverableEntryException | Phân biệt file đã mở được với entry chưa được giải mã. |
| **Alias không tồn tại** | getEntry(alias,...) trả null theo contract khi không có entry | Kiểm tra alias theo cấu hình, không cast null; không tự tạo khóa thay thế. |
| **getProtectionParameter trước getKeyStore** | IllegalStateException | Tuân thủ lifecycle của Builder. |
| **Builder từ KeyStore chưa load** | IllegalArgumentException | Load KeyStore trước khi bọc Builder. |
| **Loại ProtectionParameter không hợp lệ với file Builder** | IllegalArgumentException | Dùng PasswordProtection hoặc CallbackHandlerProtection được hỗ trợ. |
| **Không hỗ trợ load(LoadStoreParameter)** | IllegalArgumentException, UnsupportedOperationException hoặc lỗi provider | Chọn overload đúng theo tài liệu provider, không đổi sang lưu plaintext. |
| **KeyStore không hỗ trợ loại entry/algorithm** | KeyStoreException hoặc lỗi provider phù hợp | Kiểm tra KeyStore type, provider và key algorithm; không tự làm yếu mật mã. |
| **PasswordProtection đã destroy** | getPassword() ném IllegalStateException | Không hủy trước khi Builder/operation cần password; tạo protection mới từ nguồn bí mật khi cần. |
| **File bị hỏng hoặc sai format** | IOException, CertificateException, NoSuchAlgorithmException tùy tình huống | Giữ bản sao dự phòng, kiểm tra integrity và format, không bỏ qua lỗi. |

Nếu Builder file-based gặp lỗi trong lần tải đầu, **đừng chỉ gọi lại getKeyStore trên cùng Builder**: theo API, lỗi được giữ lại. Sửa nguyên nhân, lấy lại secret và tạo Builder mới; các cơ chế retry/health check nên thuộc tầng orchestration có giới hạn và audit.

Một thông báo cho người dùng cuối thường chỉ cần lỗi chung phù hợp ngữ cảnh; log vận hành có thể ghi path logic/alias/key ID/error class **không nhạy cảm**, không ghi password/PIN, private key hoặc stream dump.

## 13. Thiết kế ứng dụng thực tế: dịch vụ ký số

Giả sử service Java phải ký thông báo giao dịch bằng private key trong KeyStore. Có thể tổ chức:

~~~text
Deployment configuration
    | type=PKCS12, path, alias, keyVersion (không chứa password)
    v
Secret manager / workload identity
    | cấp password theo quyền
    v
Key loading component
    | KeyStore.Builder hoặc KeyStore.load
    | getEntry(alias, entryProtection)
    v
SigningService
    | kiểm tra key usage/policy, chuẩn hóa message bytes
    | Signature instance riêng từng request
    v
signature + algorithm/keyVersion metadata
~~~

Các bất biến:

1. **Đường dẫn, type, alias và thuật toán** đến từ cấu hình được phép, không do request tùy ý chỉ định.
2. **Secret retrieval** qua nguồn được phân quyền, với timeout, audit và cache phù hợp; không lưu password trong code.
3. **KeyStore được load** thành công và entry type được kiểm tra trước khi dùng. PrivateKeyEntry còn cần certificate chain và trust/usage policy thích hợp.
4. **Mỗi request** tạo một Signature instance phù hợp, không dùng một Signature mutable chung khi ký đồng thời.
5. **Key version** được gắn với signature để phía xác minh chọn public key đúng; rotation có chiến lược chuyển tiếp/thu hồi.
6. **Nếu khóa/phần cứng lỗi**, từ chối ký thay vì tự sinh khóa mới làm thay đổi danh tính hay chuyển sang secret hardcoded.
7. **Không xuất private key** chỉ để “kiểm tra cho chắc”: với HSM, getEncoded có thể trả null, và test byte[] của demo không áp dụng cho non-exportable key.

### 13.1. Ví dụ ứng dụng mã hóa bằng secret key

Một dịch vụ dùng SecretKeyEntry cho AES-GCM cần lưu ý thêm: keystore lưu **khóa**, không tự sinh nonce/IV đúng cho từng message, không mã hóa dữ liệu thay bạn. Với AES-GCM phải dùng IV duy nhất theo **cùng khóa** ở mỗi phép mã hóa, kiểm tra tag khi giải mã và thiết kế key rotation theo record version. Builder không tự mang lại bảo đảm đó.

### 13.2. Khi nào dùng CallbackHandlerProtection?

Khi secret không được lấy sớm và các consumer muốn load key lazily, cấu hình CallbackHandler có thể phù hợp. Tuy nhiên lifecycle của callback và rotation phải được đồng bộ với thời điểm file Builder thực sự load, đồng thời tránh prompt GUI/terminal trong web server. Với token/HSM, hãy tuân thủ hướng dẫn provider cụ thể về việc cấp PIN, session và password callback.

## 14. Kế hoạch kiểm thử cho Builder, LoadStoreParameter và password

| Test | Thao tác | Kỳ vọng |
| --- | --- | --- |
| **Tạo kho trống** | KeyStore.getInstance("PKCS12") + load(null,password) | Kho initialized, chưa có entry. |
| **Ghi SecretKeyEntry** | Sinh AES key, setEntry với password hợp lệ, store | Tạo file/byte PKCS12 dùng được trên provider đã chọn. |
| **Builder lazy load** | Tạo file Builder rồi gọi getKeyStore | getKeyStore thực sự mở file. |
| **Builder cache** | Gọi getKeyStore hai lần với file overload | Cùng KeyStore instance. |
| **getProtectionParameter lifecycle** | Gọi trước và sau getKeyStore | Trước load lỗi; sau load có protection phù hợp. |
| **Khôi phục entry** | getEntry(alias, protection) | Đúng key/certificate theo entry type. |
| **Sai file password** | Builder mới với mật khẩu sai rồi getKeyStore | Bị từ chối; không xuất khóa. |
| **Sai entry password** | Kho load đúng, getEntry với password sai | Từ chối hoặc exception phù hợp provider. |
| **Alias thiếu** | getEntry alias không có | Xử lý null; không dùng key giả hoặc fallback. |
| **PasswordProtection lifecycle** | destroy rồi isDestroyed/getPassword | isDestroyed true; getPassword không còn cho truy cập. |
| **LoadStoreParameter** | Custom lambda -> PasswordProtection; load(params) | Hành vi được xác định theo provider, không suy ra mọi provider hỗ trợ. |
| **Store/load round-trip** | store(OutputStream,char[]) rồi load(InputStream,char[]) | Khôi phục đúng trên môi trường được kiểm thử. |
| **Corrupt/truncated file** | File sai format/đứt giữa | Lỗi có kiểm soát; không tự khởi tạo mới để ghi đè bản cũ. |
| **Provider matrix** | JDK/provider/PKCS11/FIPS khác nhau | Chỉ chọn type/algorithm/params được policy cho phép. |
| **Rotation** | Cập nhật file/password/key ID khi request đang hoạt động | Không tự hot reload Builder cũ; chuyển sang instance mới có kiểm soát. |
| **Concurrency** | Nhiều request đọc khóa và ký song song | Không trộn trạng thái, không làm mất entry hoặc hỏng store. |
| **Logging** | Giả lập mọi nhánh lỗi | Không để password, private/secret key bytes lọt log/telemetry. |

Các chương trình chạy minh họa ở phần 7–8 kiểm tra **đúng key, wrong password, file Builder cache, LoadStoreParameter và destroy**. Với production còn phải có integration test cho file permission, HSM timeout/slot, key alias/rotation, certificate chain và policies.

## 15. Sai lầm thường gặp

1. **Đặt password keystore trực tiếp trong source hoặc commit vào Git.** Mọi người có quyền đọc code/bản build có thể lấy password.
2. **Đưa password vào CLI args hoặc log** để tiện debug, làm lộ qua process listing/observability.
3. **Mở một file bằng load(null,password)** rồi nghĩ đã đọc file. Null stream khởi tạo kho rỗng theo provider.
4. **Dùng getProtectionParameter trước getKeyStore.** Sai lifecycle Builder.
5. **Giả định file Builder luôn reload khi file thay đổi.** Nó giữ cùng KeyStore sau load đầu.
6. **Giả định loại Builder không file cũng cache cùng object.** Với overload type/provider/protection, contract nói mỗi getKeyStore tạo KeyStore mới.
7. **Coi getProtectionParameter(alias) là mật khẩu riêng của mọi entry.** File Builder trả password đã dùng load kho; entry có thể cần secret khác.
8. **Tự truyền LoadStoreParameter cho mọi provider rồi mong tự tìm file.** Interface không chứa path; semantics do provider.
9. **Dùng store(LoadStoreParameter) như thay thế phổ quát cho OutputStream.** Provider có thể không hỗ trợ.
10. **Chỉ Arrays.fill char[] caller mà không destroy PasswordProtection.** Constructor đã clone password.
11. **Destroy PasswordProtection trước khi lazy Builder load.** Lúc cần mở khóa sẽ không còn password.
12. **Coi char[] bảo đảm xóa sạch mọi secret khỏi heap/native memory.** Còn bản sao trong framework, callback, dumps.
13. **Dùng cùng file, password và key cho dev/prod.** Tăng blast radius và khó rotate an toàn.
14. **Cho user request chọn alias/key ID tùy ý.** Có thể dùng nhầm khóa hoặc vượt quyền nghiệp vụ.
15. **In raw key bytes để xác nhận round-trip thành công.** Dùng kiểm thử boolean, không tiết lộ key.
16. **Lưu file mới đè file cũ trực tiếp không có chiến lược atomic/backup.** Crash có thể phá hủy kho.
17. **Tái sử dụng một Cipher/Signature mutable giữa các thread.** KeyStore không bảo đảm an toàn trạng thái của engine.
18. **Chờ HSM xuất private key khi cần ký.** HSM có thể cố ý không cho export; thực hiện operation thông qua provider/key handle.
19. **Chấp nhận cert chỉ vì nằm trong KeyStore.** Cần nguồn tin cậy, chain/usage/identity policy cụ thể.
20. **Bắt mọi lỗi rồi silently tạo khóa mới.** Có thể mất khả năng giải mã dữ liệu cũ và thay đổi danh tính ký số.

## 16. Câu hỏi tự kiểm tra

**1. KeyStore.Builder giúp tránh mở file ngay lúc newInstance hay không?**  
Có, với file Builder, việc load được kích hoạt khi gọi **getKeyStore lần đầu**. Các lần sau dùng cùng KeyStore đã load.

**2. Có được gọi builder.getProtectionParameter(alias) trước getKeyStore không?**  
Không. API có thể ném **IllegalStateException**; gọi getKeyStore trước.

**3. File Builder đã tải keystore rồi, nếu file mới xuất hiện do rotation thì builder cũ tự đọc lại không?**  
Không. Phải xây dựng chiến lược reload và thường tạo builder/keystore mới.

**4. PasswordProtection nhận char[] thì sau khi xóa mảng đầu vào có chắc secret trong protection đã bị xóa?**  
Không. Constructor clone mảng. Phải **destroy()** protection riêng sau khi không còn dùng, đồng thời xóa mảng gốc.

**5. PasswordProtection.getPassword có trả bản sao không?**  
Không. Java 17 API nói nó trả một **tham chiếu tới mảng nội bộ**; cần bảo vệ và không sửa/giữ lâu.

**6. LoadStoreParameter chỉ chứa PasswordProtection có đủ để chỉ ra file PKCS12 phải đọc không?**  
Không. Interface không mang đường dẫn; provider hoặc overload khác phải xác định nguồn dữ liệu.

**7. store(LoadStoreParameter) có chắc chạy trên mọi KeyStore type không?**  
Không. Phải kiểm tra provider hỗ trợ. Khi dùng file-based PKCS12, **store(OutputStream,char[])** rõ ràng hơn.

**8. Sai password mở kho và sai entry password có phải cùng một lỗi?**  
Không. Mở file có thể gặp IOException hoặc Builder KeyStoreException; truy cập entry có thể gặp UnrecoverableEntryException.

**9. Có thể lưu private key HSM thành file bằng privateKey.getEncoded không?**  
Không chắc và thường không được phép. Key handle không xuất được có thể trả null; dùng operation qua provider/HSM.

**10. char[] được xóa trong finally có loại bỏ mọi bản sao từ callback/HTTP framework không?**  
Không. Xóa chỉ mảng được sở hữu; cần thiết kế giảm bản sao, không log và lifecycle toàn hệ thống.

## 17. Kết luận và tài liệu chính thức

**KeyStore.Builder** tách cấu hình nguồn khóa khỏi thời điểm load, nhưng không phải hot reload hay quản lý khóa tự động. **LoadStoreParameter** cung cấp một interface cho tham số load/store, còn ý nghĩa thực tế tùy provider. **PasswordProtection** lưu bản sao password và hỗ trợ destroy; **CallbackHandlerProtection** có thể trì hoãn việc yêu cầu password nhưng không xóa rủi ro secret tồn tại trong memory.

Thiết kế ứng dụng an toàn cần kết hợp **nguồn password tin cậy, giới hạn quyền truy cập, đúng lifecycle, phân biệt store/entry protection, kiểm soát file/HSM, xử lý lỗi và rotation có kiểm thử**. Hai ví dụ Java 17 minh họa cơ chế chạy thực tế, không thay thế các biện pháp vận hành production.

Tài liệu đối chiếu:

- [Java SE 17 — KeyStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html)
- [Java SE 17 — KeyStore.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.Builder.html)
- [Java SE 17 — KeyStore.LoadStoreParameter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.LoadStoreParameter.html)
- [Java SE 17 — KeyStore.PasswordProtection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.PasswordProtection.html)
- [Java SE 17 — KeyStore.CallbackHandlerProtection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.CallbackHandlerProtection.html)
- [Java SE 17 — PasswordCallback](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/callback/PasswordCallback.html)
- [Java SE 17 — KeyStoreSpi](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStoreSpi.html)
- [Java SE 17 — Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html)