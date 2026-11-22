# Xác minh nguồn gốc, tính toàn vẹn và phiên bản của tệp nhị phân phát hành

## 1. Vì sao phải kiểm tra trước khi nạp thư viện native?

Một ứng dụng Java có thể nạp thư viện native qua JNI (`System.load`, `System.loadLibrary`), dùng Foreign Function & Memory API (FFM) để tra cứu hàm trong thư viện, hoặc phân phối một executable/agent native kèm theo. Tệp `.so` (Linux), `.dylib` (macOS), `.dll` (Windows) là **mã máy**, có thể truy cập tài nguyên của tiến trình và ảnh hưởng trực tiếp đến tính toàn vẹn của JVM. Tên tệp đúng chưa chứng minh được nội dung an toàn hay tương thích.

Trước khi phát hành, tải xuống hoặc triển khai một binary, cần trả lời bốn câu hỏi có liên quan nhưng **khác nhau**:

1. **Nguồn gốc (provenance / authenticity):** Ai đã tạo và công bố tệp? Nó xuất phát từ source repository, commit, quy trình build và nhà phát hành nào? Có chứng cứ mật mã ràng buộc tệp với danh tính được tin cậy không?
2. **Tính toàn vẹn (integrity):** Các byte nhận được có khớp chính xác artifact đã được phê duyệt không? Digest SHA-256 và chữ ký có hợp lệ không?
3. **Phiên bản (version identity):** Đúng release, build, commit và ABI contract mà ứng dụng cần chứ? Có phải bản đã được kiểm thử và duyệt phát hành không?
4. **Khả năng tương thích (compatibility):** Binary có chạy trên OS, CPU, libc/ABI và JDK đích, với đầy đủ native dependencies và exported symbols không?

**Kết luận kiểm soát:** Một tệp có SHA-256 trùng nhưng lấy digest từ nguồn không đáng tin vẫn chưa xác thực được nhà phát hành. Một chữ ký hợp lệ nhưng thuộc người ký không nằm trong danh sách cho phép cũng chưa đủ. Một binary đúng tên phiên bản có thể vẫn sai kiến trúc hoặc bị thay nội dung sau phát hành.

## 2. Phân biệt các loại bằng chứng

| Bằng chứng | Chứng minh được gì khi kiểm tra đúng? | Giới hạn cần nhớ |
| --- | --- | --- |
| Tên file như `nativebridge-2.4.1-linux-x86_64.so` | Gợi ý release và nền tảng dự định | Có thể đổi tên tùy ý; không xác thực nội dung |
| SHA-256 của tệp | Nội dung khớp digest kỳ vọng | Digest kỳ vọng phải đến từ manifest đã được xác thực hoặc nguồn tin cậy độc lập |
| Chữ ký số của artifact/manifest | Dữ liệu đã được ký bởi khóa/danh tính xác minh được, không bị thay đổi so với nội dung đã ký | Phải đối chiếu danh tính publisher, trust root, chính sách thời gian/thu hồi; ký không đồng nghĩa code không có lỗ hổng |
| Build provenance / attestation (ví dụ SLSA, in-toto) | Có thể ràng buộc artifact digest với builder, source commit và thông tin quy trình build | Chỉ có ý nghĩa sau khi kiểm tra chữ ký, subject digest, builder/source identity và policy mong đợi |
| Metadata `version`, Git tag, build ID | Hỗ trợ truy vết release/build và chọn version đúng | Tag có thể bị dịch chuyển, metadata có thể bị giả mạo nếu artifact chưa được xác thực |
| SBOM | Liệt kê thành phần/phụ thuộc được khai báo của build | SBOM không phải chữ ký hay tự động chứng minh danh sách đã đầy đủ; cũng cần xác thực và đối chiếu artifact |
| ELF `SONAME`, Mach-O version, Windows `FileVersion` | Cung cấp một phần thông tin ABI hoặc metadata phiên bản | Không nhất thiết đồng nhất với semantic version; không thay thế digest và test tương thích |

### Nguồn tin cậy đến từ đâu?

Một thứ tự đánh giá khả dụng:

- **Nguồn phân phối được phê duyệt:** release chính thức của nhà cung cấp hoặc registry/package repository có kiểm soát; pin phiên bản và artifact cụ thể, tránh tải tùy ý từ mirror không được công nhận.
- **Danh tính publisher được xác minh độc lập:** public key/certificate, tên tổ chức, Sigstore certificate identity + OIDC issuer hoặc khóa ký package đã được phân phối theo kênh tin cậy **trước** khi kiểm tra tệp.
- **Digest ràng buộc vào thông tin có chữ ký:** chữ ký trực tiếp trên binary, signed manifest hoặc attestation chứa digest của artifact. Kiểm tra chữ ký của đối tượng **thực sự bao phủ digest** của tệp nhận được.
- **Nguồn và build:** source repository được phê duyệt, commit cụ thể, build workflow và builder identity; kiểm tra giá trị này với kỳ vọng của tổ chức thay vì chỉ thấy “attestation valid”.
- **Quyền truy cập và tính bất biến:** tag release, artifact bucket và repository package phải có chính sách tránh ghi đè; ghi nhận digest tại thời điểm chấp thuận.

Tải `library.so` và `SHA256SUMS` từ cùng một trang đã bị chiếm quyền rồi so sánh hai file **không đủ chống lại kẻ tấn công** có thể thay cả binary lẫn checksum. HTTPS giúp bảo vệ quá trình truyền nhưng không thay thế đánh giá danh tính release, chữ ký và trust root.

## 3. Thiết kế thông tin định danh của một native release

Với mỗi artifact, release manifest nên cung cấp thông tin rõ ràng, có thể kiểm tra bằng máy:

| Trường | Ý nghĩa |
| --- | --- |
| Artifact name, size, SHA-256 | Định danh chính xác các byte được duyệt |
| Release version và build number | Phiên bản công bố; build number giúp phân biệt nhiều build trong cùng version |
| Source repository và commit SHA đầy đủ | Gắn phiên bản với mã nguồn cụ thể; không chỉ ghi tên branch |
| Build workflow, builder identity, toolchain/compiler | Truy vết ai/công cụ nào đã tạo binary |
| Target OS, CPU architecture, ABI/libc baseline | Phân biệt Linux x86-64 glibc với Linux aarch64/musl, Windows x64, macOS arm64… |
| Exported API/ABI version và native dependencies | Kiểm tra tên symbol, kiểu tham số, calling convention, runtime dependencies |
| Min/max supported JDK hoặc phạm vi tương thích đã kiểm thử | Kỳ vọng Java runtime và JNI/FFM binding |
| Publisher identity, signature/bundle, attestation | Đầu vào cho verify chữ ký/provenance bằng policy |
| SBOM và thông tin phát hành | Phục vụ inventory, phân tích lỗ hổng và truy vết |

**Phân biệt version với artifact identity:** cùng một version `2.4.1` đôi khi được build lại cho kiến trúc khác, dùng compiler khác hoặc sửa bản phát hành; digest sẽ khác. Nếu một release version cho phép nhiều target, cần có danh sách **digest riêng cho từng artifact**. Chỉ dùng `2.4.1` hoặc tên thư mục để xác minh là không đủ. Trường version tự nhúng trong binary cũng có thể bị sửa; chỉ đáng tin sau khi xác minh artifact.

Ghi version qua semantic versioning có ích để mô tả thay đổi API, nhưng **ABI compatibility không tự động được bảo đảm bởi tên major/minor/patch**. Bản binary JNI/FFM vẫn phải kiểm tra symbol, data layout, calling convention và phiên bản dependency thực tế.

## 4. Quy trình xác minh đầy đủ trước khi nạp/chạy

### Bước 1 — Pin release và chính sách danh tính kỳ vọng

Xác định từ tài liệu release đáng tin: publisher, repo/commit hoặc tag được phê duyệt, target OS/architecture, artifact digest và khóa ký hoặc danh tính ký được phép. Phân biệt rõ **điều được kỳ vọng trước khi tải** với thông tin do chính tệp vừa tải tự công bố. Với Sigstore keyless, policy phải chỉ định **certificate identity và OIDC issuer** mong đợi; chấp nhận “bất kỳ chữ ký hợp lệ nào” là chưa đủ.

Không dùng tag trôi nổi như `latest` để xác nhận một build đã duyệt. Khi triển khai OCI container, khóa image theo **image digest** thay vì chỉ theo tag; sau đó vẫn xác minh từng native binary mà pipeline trích ra nếu cần truy vết độc lập.

### Bước 2 — Tải và đặt vào vùng staging không thực thi

Lưu artifact và bằng chứng kèm theo (manifest, signature, verification bundle, attestation, SBOM) trong staging có kiểm soát quyền ghi. Chưa gọi `System.load`, chạy binary hay chạy script đính kèm từ artifact chưa xác thực. Giữ tên và đường dẫn của file đã kiểm tra; không chuyển sang một file khác cùng tên sau khi xác minh.

Khi artifact đến từ zip/tar, cần phòng path traversal, symbolic link không mong đợi và việc extract đè file ngoài staging. Với thư viện native, phụ thuộc được dynamic loader nạp **cũng là mã thực thi**, cần có nguồn gốc và phạm vi tìm kiếm đáng tin.

### Bước 3 — Tính SHA-256 độc lập trên đúng file đã tải

Linux:

```bash
sha256sum nativebridge-2.4.1-linux-x86_64.so
```

macOS:

```bash
shasum -a 256 libnativebridge.dylib
```

Windows PowerShell:

```powershell
Get-FileHash -LiteralPath .\nativebridge.dll -Algorithm SHA256
```

Các lệnh trên chỉ **tính** digest, không tự quyết định file đáng tin. So sánh 64 ký tự hex với digest của **đúng artifact/target** trong manifest đã được xác thực. Bất kỳ sai khác nào phải dừng quá trình sử dụng, kiểm tra lại đường dẫn/tên file và báo lỗi. Không bỏ qua cảnh báo do “chỉ lệch một ký tự”.

Chọn SHA-256 hoặc thuật toán mạnh đã được policy chấp nhận. Không dùng MD5/SHA-1 cho mục tiêu chống sửa đổi có chủ đích. Hash khớp với nguồn độc lập/signed manifest cho thấy tính toàn vẹn của **bytes**, không tự chứng minh chức năng, độ an toàn hoặc ABI.

### Bước 4 — Xác minh chữ ký và provenance

Nếu nhà phát hành có chữ ký detached/certified release, kiểm tra chữ ký với **trust root được cấp sẵn ngoài artifact**, sau đó khớp signer identity với allowlist. Khi dùng Sigstore/Cosign keyless, có thể xác minh một blob và verification bundle bằng dạng lệnh:

```bash
cosign verify-blob release.bin --bundle release.sigstore.json --certificate-identity signer@example.org --certificate-oidc-issuer https://accounts.google.com
```

Đây là **ví dụ minh họa giao diện lệnh**: `release.bin`, `release.sigstore.json` và danh tính email/issuer phải thay bằng giá trị thực tế do **nhà phát hành đã được xác thực** cung cấp; không mặc nhiên tin `signer@example.org`. Chỉ kết luận PASS khi chữ ký/bundle hợp lệ, identity/issuer đúng policy và nội dung được ký ràng buộc **digest của artifact cần phát hành**. Cơ chế chứng minh thời điểm ký/transparency-log cũng cần được kiểm tra theo cách công cụ hỗ trợ.

Nếu nhận SLSA/in-toto attestation, ngoài xác thực chữ ký còn phải đối chiếu:

1. `subject` có đúng SHA-256 của file đang kiểm tra không?
2. `builder.id` và build system có nằm trong danh sách được phê duyệt không?
3. Source repository, revision/commit, build type, workflow và external parameters có đúng dự kiến không?
4. Dependency/source materials được khai báo có tương ứng release đã chọn không?
5. Nếu attestation thiếu, sai subject hoặc dùng builder ngoài policy, pipeline **FAIL**, kể cả signature có thể hợp lệ về mặt mật mã.

**Không nhầm lẫn:** provenance cho biết điều kiện và quy trình tạo artifact, nhưng không bảo đảm mã nguồn không có lỗi hoặc builder chưa từng bị xâm phạm; đó là một lớp bằng chứng để kiểm soát rủi ro chuỗi cung ứng.

### Bước 5 — Kiểm tra file format, OS/CPU và phụ thuộc native

Các lệnh dưới đây là **lệnh kiểm tra metadata cho binary đã được xác minh**. Chúng không phải bước kiểm tra chữ ký.

| Nền tảng | Lệnh thường dùng | Đọc điều gì? |
| --- | --- | --- |
| Linux | `file nativebridge.so`, `readelf -h nativebridge.so` | ELF class 32/64-bit, `Machine`, endian, kiểu ELF |
| Linux | `readelf -d nativebridge.so` | `SONAME`, `NEEDED`, `RPATH` / `RUNPATH` và phụ thuộc dynamic |
| Linux | `readelf -Ws nativebridge.so`, `readelf --version-info nativebridge.so` | Exported symbols, versioned symbols/GLIBC requirements |
| macOS | `file libnativebridge.dylib`, `otool -hv libnativebridge.dylib` | Mach-O architecture và header |
| macOS | `otool -L libnativebridge.dylib` | Install names, phụ thuộc, compatibility/current version của dylib |
| Windows | `dumpbin /headers nativebridge.dll`, `dumpbin /dependents nativebridge.dll` | PE machine type, DLL dependencies (cần Visual Studio Build Tools) |
| Windows | `dumpbin /exports nativebridge.dll` | Exported symbols |
| Windows PowerShell | `(Get-Item .\nativebridge.dll).VersionInfo` | FileVersion/ProductVersion nếu publisher đã nhúng |

Ví dụ Linux:

```bash
file nativebridge.so
readelf -h nativebridge.so
readelf -d nativebridge.so
readelf -Ws nativebridge.so
readelf --version-info nativebridge.so
```

Kết quả thực tế phụ thuộc file đang kiểm tra; không có một stdout cố định đúng cho mọi thư viện.

**Cần đối chiếu** cả kiến trúc CPU và ABI: Linux x86-64 glibc khác Linux x86-64 musl; Windows PE khác Linux ELF; macOS arm64 khác x86_64 (trừ khi artifact là universal/fat binary chứa architecture phù hợp). Một ELF đúng architecture vẫn có thể cần GLIBC mới hơn máy đích. Đồng thời xem loader search path: `RPATH/RUNPATH`, `java.library.path`, đường dẫn phụ thuộc DLL, `@rpath`/`@loader_path` trên macOS. Các phụ thuộc bị thay trên search path có thể dẫn đến load binary khác với file đã kiểm tra.

Trên Linux, ưu tiên `readelf`/`objdump` để **kiểm tra tĩnh** metadata của file chưa tin cậy. `ldd` hữu ích để biết thư viện sẽ resolve ở môi trường hiện tại nhưng với file không đáng tin hoặc loader khác nhau, việc dùng nó có thể có rủi ro; chỉ thực hiện sau bước xác thực và trong môi trường kiểm soát.

### Bước 6 — Kiểm tra code signing phù hợp nền tảng

**Windows:** Nếu publisher dùng Authenticode, đọc trạng thái, chứng thư và nhận diện nhà phát hành, không chỉ xem `Status=Valid`.

```powershell
$sig = Get-AuthenticodeSignature -LiteralPath .\nativebridge.dll
$sig | Select-Object Status, SignerCertificate
```

`Get-AuthenticodeSignature` chỉ khả dụng trên Windows. Verify phải đối chiếu publisher/certificate chain với chính sách của tổ chức; file không ký hoặc ký bởi người không được cho phép không vượt qua kiểm tra nguồn gốc chỉ nhờ SHA-256 tự công bố.

**macOS:** Nếu phát hành dylib/app đã ký, kiểm tra chữ ký và thông tin signing identity:

```bash
codesign --verify --verbose=2 libnativebridge.dylib
codesign -dv --verbose=4 libnativebridge.dylib
```

Kết quả `codesign --verify` cơ bản xác nhận tính nhất quán của chữ ký trên code đã ký; để khẳng định **đúng nhà phát hành**, còn cần đối chiếu designated requirement, Team ID/certificate identity và chính sách tin cậy thích hợp. Ad-hoc signature hoặc chữ ký tự ký không mặc nhiên đại diện cho publisher được phê duyệt. Notarization/Gatekeeper, nếu liên quan đến gói phân phối, là một kiểm tra khác với provenance của bản build.

**Linux:** Nhiều `.so` không nhúng chữ ký theo một chuẩn chung như Authenticode. Cần dùng chữ ký detached, signed package metadata (ví dụ package manager) hoặc attestation có xác thực; riêng `readelf` không xác minh publisher. Kiểm tra identity của repository/package signing key độc lập.

### Bước 7 — Đối chiếu phiên bản và ABI contract với ứng dụng

Trước khi đưa binary vào production, kiểm tra các lớp version sau:

- **Release version:** manifest và release notes có cùng bản đã được duyệt không? Target artifact của OS/CPU có đúng release đó không?
- **Source/build identity:** source commit, toolchain, build number và artifact digest có khớp attestation không?
- **Embedded file metadata:** Windows `FileVersion/ProductVersion`, Linux `SONAME`/build ID (nếu có), Mach-O `current_version` / `compatibility_version`. Đây là **metadata phục vụ đối chiếu**, không nhất thiết bằng release semver và không thay cho chữ ký.
- **ABI/contract:** exported JNI names, C symbols cho FFM, calling convention, alignment/layout, size của struct, ownership của memory, tên/hành vi API; với JNI còn có quy ước `JNI_OnLoad` và JNI version nếu thư viện dùng. Mismatch có thể gây lỗi linker, dữ liệu sai hoặc crash.
- **Runtime compatibility:** supported JDK/JNI version, OS patch, libc/C runtime, native dependency versions, CPU instruction set.
- **Artifact thực được nạp:** sau xác minh, kiểm tra ứng dụng dùng chính đường dẫn/version/digest đã duyệt. `System.load` dùng absolute path; `System.loadLibrary` tìm theo tên logical và loader search configuration, vì vậy có nguy cơ nạp file cùng tên khác.

Nếu có hai build cùng version nhưng digest khác, **không hợp thức hóa bằng cách chỉ kiểm tra tên version**. Phải biết đó là build được phê duyệt, đúng source/attestation và đúng OS/ABI. Reproducible build có thể giúp đối chiếu output từ cùng nguồn/build recipe nếu quy trình thực sự deterministic; không phải mọi binary đều reproducible mặc định vì timestamp, đường dẫn hoặc metadata biên dịch.

## 5. Bài thực hành Java 17+: tự kiểm tra SHA-256 của tệp

Ví dụ sau chỉ **đọc byte và so digest**, không nạp hoặc thực thi thư viện. Nó hữu ích như một gate độc lập trước khi dùng JNI/FFM. SHA-256 kỳ vọng phải được cung cấp từ **signed release manifest đã xác minh**, không phải lấy tùy tiện cùng URL với binary mà chưa kiểm tra danh tính.

Tạo file **`VerifyBinary.java`**:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public final class VerifyBinary {
    private VerifyBinary() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2 || !args[1].matches("(?i)[0-9a-f]{64}")) {
            System.err.println(
                    "Usage: java VerifyBinary <file> <trusted-sha256-hex>");
            System.exit(2);
            return;
        }

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream input = Files.newInputStream(Path.of(args[0]))) {
            byte[] buffer = new byte[8192];
            int size;
            while ((size = input.read(buffer)) != -1) {
                if (size > 0) {
                    digest.update(buffer, 0, size);
                }
            }
        }

        byte[] actual = digest.digest();
        byte[] expected = HexFormat.of().parseHex(args[1]);

        if (MessageDigest.isEqual(expected, actual)) {
            System.out.println("SHA-256 OK");
        } else {
            System.out.println("SHA-256 MISMATCH");
            System.exit(1);
        }
    }
}
```

**Giải thích:** `Files.newInputStream` đọc theo block để không cần đưa toàn binary vào RAM; `MessageDigest.getInstance("SHA-256")` tính digest của **nội dung file thực**; `HexFormat` của Java 17 chuyển 64 ký tự hex thành 32 byte; `MessageDigest.isEqual` so sánh hai digest. Chương trình chỉ trả `SHA-256 OK` khi chúng bằng nhau, và trả exit code `1` khi không khớp; đối số sai dùng exit code `2`. Lỗi đọc file được báo qua exception và tiến trình không đạt gate.

Để kiểm chứng bằng dữ liệu đã biết thay vì binary giả định, tạo file thử gồm **đúng ba byte ASCII `abc`, không có ký tự xuống dòng**.

Trên Linux/macOS:

```bash
printf 'abc' > sample.bin
javac VerifyBinary.java
java VerifyBinary sample.bin ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

Trên Windows PowerShell (tạo đúng ba byte ASCII và sử dụng cùng `javac`/`java`):

```powershell
[System.IO.File]::WriteAllBytes('sample.bin', [Text.Encoding]::ASCII.GetBytes('abc'))
javac VerifyBinary.java
java VerifyBinary sample.bin ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

**Stdout chính xác** của lệnh chạy với file `abc`:

```text
SHA-256 OK
```

Nếu truyền một SHA-256 64 ký tự hex không khớp (ví dụ toàn số 0), cùng file `abc` sẽ cho:

```text
SHA-256 MISMATCH
```

Với mismatch, chương trình thoát bằng mã `1`, thuận tiện cho CI từ chối release. Ví dụ này chứng minh tính đúng đắn của phép so digest; **không** chứng minh `sample.bin` là native binary an toàn. Khi thay bằng file native thật, dùng SHA-256 của artifact đã phê duyệt và xác minh chữ ký/attestation của nguồn chứa digest.

### Lưu ý chống thay file sau khi xác minh

Luồng `verify(file A) → một tác nhân sửa file → load(file A)` có thể mắc **time-of-check/time-of-use (TOCTOU)**. Đặt artifact trong thư mục staging/deploy bất biến hoặc chỉ cấp quyền đọc cho runtime sau khi kiểm tra; không tải/ghi đè hoặc thay symlink ở cùng đường dẫn giữa verify và `System.load`. Xác nhận những native dependencies mà loader resolve cũng từ nguồn được kiểm soát. Việc in checksum trong startup log hữu ích để truy vết build, nhưng log không thay thế cơ chế buộc ứng dụng dùng đúng file đã xác minh.

## 6. Quy trình CI/CD: xác thực và chặn phát hành sai

Có thể tổ chức các gate theo chuỗi:

```text
Build native cho từng OS/CPU target
  -> Unit + JNI/FFM integration tests trên target phù hợp
  -> Ghi source commit, compiler, ABI/version và SHA-256 từng artifact
  -> Sinh provenance / SBOM và ký artifact hoặc manifest/attestation
  -> Publish bất biến (artifact + bằng chứng)
  -> Download về môi trường xác minh độc lập
  -> VERIFY signer/trust root + provenance policy + artifact digest
  -> VERIFY file format/architecture/dependency + release/ABI version
  -> Smoke test nạp và gọi chức năng JNI/FFM trong môi trường cô lập
  -> Promote đúng digest vào kênh phát hành hoặc triển khai
```

Một bộ quy tắc pass/fail minh bạch:

| Gate | PASS khi nào? | FAIL khi nào? |
| --- | --- | --- |
| Nguồn gốc | Signer/issuer, publisher, builder, source commit đúng policy và artifact subject match | Không xác minh được, danh tính lạ, provenance thiếu/sai hoặc commit không được duyệt |
| Toàn vẹn | SHA-256 của **bytes đang phát hành** khớp digest đã xác thực | Khác digest hoặc không có nguồn digest đáng tin |
| Version | Release/build/commit và đúng artifact target được duyệt | Tệp trùng tên nhưng version/commit/digest khác hoặc release đã bị thay |
| Tương thích | OS/CPU/ABI/JDK, symbol, loader deps và test native đạt | Sai architecture, thiếu dependency, ABI mismatch, load hoặc smoke test lỗi |
| Triển khai | Artifact bất biến, đúng digest được pin, log đủ định danh | Triển khai lại tag trôi nổi hoặc thay binary sau verify |

Thông tin kiểm toán tối thiểu cần lưu gồm: artifact digest, release version, source revision, builder + signer identity, kết quả xác minh, thời điểm và môi trường test, file thực đã promote. Trong CI/CD, **thiếu thông tin xác thực là trạng thái không đạt**, không được âm thầm cho qua chỉ vì tệp tải xuống thành công.

## 7. Các tình huống sai phổ biến

1. **“Checksum đúng vì file `SHA256SUMS` cùng thư mục nói vậy.”** Nếu cả file và checksum đến từ nguồn bị thay đổi, không có bằng chứng độc lập về tính xác thực. Cần chữ ký/manifest được xác minh bằng khóa hoặc danh tính được chấp thuận.
2. **“Chữ ký valid nên tất cả đều an toàn.”** Signer phải đúng publisher dự kiến; chữ ký không bảo đảm không có lỗi logic, mã độc từ source hoặc dependency vulnerability.
3. **“Cùng phiên bản `2.4.1` là cùng binary.”** Build theo nền tảng hoặc build lại có digest khác. Version label không thể thay artifact digest.
4. **“`readelf` thấy đúng x86-64 thì thư viện chắc chắn chạy.”** Vẫn có thể sai libc, GLIBC symbol version, instruction set, dependencies, FFM layout hoặc JNI ABI.
5. **“Windows `FileVersion`, macOS `current_version`, Linux `SONAME` là bằng chứng nhà phát hành.”** Chúng là metadata/ABI hint, có thể bị giả mạo khi chưa xác minh chữ ký/digest.
6. **“Đã xác minh `libnative.so` thì đủ.”** Dynamic loader có thể nạp dependency native khác ở search path bị kiểm soát; bundle và dependency chain cũng cần được quản lý.
7. **“Kiểm tra xong rồi cứ thay file cùng tên cũng được.”** Đó là nguy cơ TOCTOU. Nên pin digest, giữ bản đã kiểm tra bất biến, ngăn write/symlink swap trước lúc load.
8. **“SBOM được đính kèm nghĩa là nguồn gốc đã được chứng minh.”** SBOM là inventory; vẫn phải kiểm tra provenance, chữ ký và tính gắn kết giữa SBOM với artifact.
9. **“Thấy lỗi `UnsatisfiedLinkError` là có vấn đề bảo mật.”** Lỗi load cũng có thể đơn giản do sai path, thiếu thư viện, symbol hoặc kiến trúc. Cần bằng chứng cụ thể, không suy luận tự động.
10. **“Thử chạy file lạ trước để xem metadata.”** Binary chưa xác thực không nên được thực thi; dùng static inspection trước, chỉ smoke test sau khi qua gate nguồn gốc/toàn vẹn trong môi trường kiểm soát.

## 8. Checklist phát hành

Trước khi đưa native library vào môi trường chạy Java, tự xác minh được từng câu sau:

- [ ] Artifact được lấy từ nguồn release được phép; release/commit/target đã được chọn rõ.
- [ ] Publisher/trust root được xác minh độc lập; chữ ký hoặc signed provenance hợp lệ và đúng policy.
- [ ] SHA-256 **thực tế** của file khớp digest đã xác thực cho đúng artifact target.
- [ ] Version, source revision, build identity và metadata liên quan nhất quán; không dùng riêng tên file làm bằng chứng.
- [ ] OS/CPU, ABI/libc, exported symbols, dependencies và supported JDK/JNI/FFM contract phù hợp.
- [ ] Thư viện và dependencies được nạp từ đường dẫn/bản đã duyệt; không có đường ghi đè sau khi verify.
- [ ] Integration/smoke test với JNI hoặc FFM qua đúng binary và môi trường target đã đạt.
- [ ] Log/manifest lưu digest, publisher, source commit và release version để truy vết hoặc rollback.

**Điểm cốt lõi:** Xác minh **ai tạo ra**, **chính xác byte nào**, **thuộc bản build/release nào** và **có chạy đúng trên môi trường mục tiêu không** là bốn lớp kiểm tra cần thực hiện cùng nhau. Với native interoperability, bỏ qua một lớp có thể khiến JVM nạp nhầm mã máy dù tên file trông hoàn toàn hợp lệ.

## Tài liệu tham khảo chính thức

- [Oracle Java 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html) và [HexFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html): tính và so sánh SHA-256 trong Java.
- [Sigstore — Cosign quickstart, verify-blob](https://docs.sigstore.dev/quickstart/quickstart-cosign/): chứng thực blob, verification bundle, signer identity và issuer.
- [SLSA — Verifying artifacts](https://github.com/slsa-framework/slsa/blob/main/spec/verifying-artifacts.md): xác minh provenance theo builder identity, subject và build policy.
- [Microsoft Learn — Get-FileHash](https://learn.microsoft.com/powershell/module/microsoft.powershell.utility/get-filehash) và [Get-AuthenticodeSignature](https://learn.microsoft.com/powershell/module/microsoft.powershell.security/get-authenticodesignature): hash và chứng thực chữ ký trên Windows.
- [Apple — Code Signing Tasks](https://developer.apple.com/library/archive/documentation/Security/Conceptual/CodeSigningGuide/Procedures/Procedures.html): cách xác minh chữ ký và designated requirement.
- [GNU binutils — readelf](https://sourceware.org/binutils/docs/binutils/readelf.html): đọc metadata ELF, symbol và dependency để kiểm tra tương thích native.