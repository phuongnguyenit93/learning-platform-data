# Quản lý hiện vật đầu vào có thể tái tạo cho JMOD

## 1. Mục tiêu và phạm vi

Quản lý hiện vật đầu vào có thể tái tạo là việc xác định, khóa phiên bản, kiểm tra tính toàn vẹn và lưu lại dấu vết của mọi tệp cùng công cụ cần thiết để tạo ra một JMOD. Khi chạy lại quy trình trong cùng điều kiện, nhóm phát triển phải có thể tạo lại cùng nội dung module; với quy trình được chuẩn hóa đầy đủ, mục tiêu cao hơn là tạo ra tệp JMOD có cùng SHA-256.

Nội dung này tập trung vào JMOD trong quy trình module của Java: chuẩn bị class files và tài nguyên, đóng gói bằng lệnh jmod, kiểm tra gói và cung cấp nó cho jlink. JMOD được giới thiệu cùng hệ thống module của Java 9. Trong công việc hiện tại, hãy dùng JDK còn được duy trì và đã khóa phiên bản; không lấy JDK 9 cũ làm môi trường build mặc định.

Cần phân biệt ba mức độ:

- **Tái lập nội dung đầu vào:** cùng commit mã nguồn, dependency, tài nguyên và cấu hình được sử dụng.
- **Tái lập cấu trúc gói:** JMOD có cùng module descriptor, đường dẫn entry và nội dung tệp.
- **Tái lập byte:** hai lần build độc lập tạo ra tệp JMOD có cùng SHA-256.

Hai mức đầu chưa tự động bảo đảm mức thứ ba. Timestamp, thứ tự entry, compiler, công cụ đóng gói hoặc dữ liệu sinh ra trong build có thể làm thay đổi byte của artifact dù nội dung logic tương đương.

## 2. JMOD nằm ở đâu trong quy trình module

JMOD là gói module dành cho công cụ JDK. Nó có thể chứa:

- Class files đã biên dịch, bao gồm module descriptor **module-info.class**.
- Tài nguyên đi kèm module.
- Native libraries và các lệnh native.
- Tệp cấu hình, header files, legal notices và man pages khi module cần các loại dữ liệu này.

Lệnh **jmod** tạo, liệt kê, mô tả hoặc giải nén JMOD. Công cụ **jlink** đọc module từ module path, giải quyết module graph và tạo runtime image tùy chỉnh.

Một JMOD không phải là JAR thông thường và không được thêm trực tiếp vào classpath để chạy ứng dụng. Nếu cần phân phối một thư viện hoặc ứng dụng module để chạy trên JDK có sẵn, hãy chọn định dạng triển khai phù hợp, thường là modular JAR. JMOD chủ yếu phục vụ bước liên kết runtime image bằng jlink.

Lệnh **jmod create** chỉ đóng gói các đường dẫn được chỉ định. Nó không biên dịch Java source, không tự tải dependency và không tự đóng gói toàn bộ module phụ thuộc. Hãy biên dịch module trước, sau đó bảo đảm mọi module cần thiết đều có mặt trên module path khi chạy jlink.

## 3. Xác định đầy đủ đầu vào

Trước khi build, tạo một danh mục đầu vào có thể kiểm tra được. Danh mục nên bao gồm các nhóm sau:

| Nhóm | Nội dung cần khóa | Cách xác minh |
|---|---|---|
| Mã nguồn | Commit, trạng thái working tree, submodule và generated source | Ghi commit ID; yêu cầu working tree sạch hoặc lưu rõ các thay đổi được phép |
| Module descriptor | **module-info.java** và kết quả biên dịch **module-info.class** | Kiểm tra **requires**, **exports**, **opens**, **uses**, **provides** bằng kết quả biên dịch và **jmod describe** |
| Class files | Toàn bộ class files được đưa vào JMOD | Lưu danh sách đường dẫn và SHA-256 |
| Resources | Properties, cấu hình mặc định, dữ liệu tĩnh và resource được sinh | Khóa nguồn sinh, encoding và quy tắc tạo tệp |
| Dependencies | Tọa độ artifact, phiên bản, repository và checksum | Dùng dependency locking hoặc cơ chế checksum verification của build tool |
| Toolchain | Nhà cung cấp JDK, phiên bản, build number, kiến trúc và checksum gói JDK | Ghi lại phiên bản của **java**, **javac**, **jmod** và **jlink** |
| Cấu hình đóng gói | Tham số jmod, thư mục staging, module version và target platform | Lưu script build trong version control |
| Native inputs | Native libraries, command và target OS/CPU | Ghi checksum, kiến trúc và nguồn build của từng tệp |

Không dựa vào một thư mục build còn sót lại từ lần chạy trước. Tạo class files và staging directory mới trong mỗi lần build. Chỉ đưa vào staging các tệp đã được khai báo; loại bỏ tệp tạm, cache, file editor, log, secret và dữ liệu máy cá nhân.

Nếu build tool tải dependency từ repository, hãy khóa phiên bản và kiểm tra checksum. Tránh phiên bản động, dependency không khóa, snapshot có thể bị thay thế hoặc tải một artifact khác nhau dưới cùng tọa độ. Giữ wrapper và cấu hình repository trong version control để các máy CI sử dụng cùng quy trình.

## 4. Khóa toolchain và môi trường build

Dùng một bản phân phối JDK cụ thể cho cả bước biên dịch, tạo JMOD và liên kết bằng jlink. Không để **PATH** vô tình chọn một JDK khác với **JAVA_HOME**.

Lưu kết quả các lệnh sau trong build log hoặc provenance manifest:

~~~bash
java --version
javac --version
jmod --version
jlink --version
jmod --help
~~~

Ngoài phiên bản JDK, ghi nhận nhà cung cấp, build number, hệ điều hành, kiến trúc CPU và checksum của gói JDK đã cài. Với module chứa native library hoặc native command, các thông tin nền tảng này là một phần của đầu vào; JMOD cho Linux x64 không thể được xem là artifact tương đương với JMOD chứa native binary cho Windows hoặc macOS.

Chuẩn hóa các yếu tố môi trường có thể ảnh hưởng đầu ra:

- Dùng locale và timezone đã xác định trong CI.
- Không đưa đường dẫn tuyệt đối của máy build, thư mục tạm ngẫu nhiên hoặc thông tin cá nhân vào tài nguyên được sinh.
- Khóa encoding và quy tắc sinh resource.
- Sắp xếp dữ liệu đầu vào trước khi tạo tệp nếu thứ tự của dữ liệu có thể thay đổi giữa các lần chạy.
- Không dùng timestamp hiện tại, số ngẫu nhiên hoặc dữ liệu từ dịch vụ bên ngoài mà không lưu lại giá trị đầu vào.
- Tách thư mục source, thư mục build, staging và output để mỗi lần chạy có thể bắt đầu từ trạng thái sạch.

JMOD và jlink nên dùng cùng dòng phát hành JDK đã được khóa. Không giả định một JMOD tạo bởi một bản JDK bất kỳ sẽ tương thích với mọi bản JDK khác.

## 5. Chuẩn bị staging directory ổn định

Staging directory là tập hợp tệp thực tế mà lệnh jmod sẽ đóng gói. Hãy tạo nó từ đầu trong mỗi lần build, theo cùng cấu trúc thư mục và quy tắc đặt tên.

Ví dụ, một module chỉ chứa class files có thể có cấu trúc:

~~~text
build/
  classes/
    module-info.class
    com/
      example/
        greetings/
          GreetingService.class
  jmods/
~~~

Nếu module cần native library hoặc dữ liệu phụ trợ, đưa chúng vào các thư mục riêng và khai báo rõ khi tạo JMOD. Không sao chép toàn bộ thư mục output của dự án vào JMOD một cách tùy tiện.

Kiểm tra các điều kiện sau trước khi đóng gói:

1. **module-info.class** thuộc đúng module dự kiến.
2. Class files và resources được tạo từ đúng commit và dependency đã khóa.
3. Mỗi tệp có một đường dẫn tương đối ổn định trong staging.
4. Không có tệp ngoài danh mục, tệp trùng tên do khác chữ hoa/chữ thường hoặc symlink trỏ ra ngoài vùng build.
5. Native files khớp với target OS và CPU.
6. Những thư mục tùy chọn không cần thiết được bỏ khỏi lệnh tạo gói.

Việc tạo staging từ đầu giúp phát hiện tệp bị xóa khỏi source nhưng vẫn còn sót trong output của lần build trước. Đây là một nguyên nhân phổ biến khiến hai artifact có nội dung khác nhau dù mã nguồn đã giống nhau.

## 6. Tạo JMOD với metadata ổn định

Dùng **jmod create** từ JDK đã khóa. Ví dụ sau đóng gói class files của module **com.example.greetings**:

~~~bash
jmod create --class-path build/classes --module-version 1.0.0 --target-platform linux-x64 --date 2025-01-01T00:00:00Z build/jmods/com.example.greetings.jmod
~~~

Các tham số có ý nghĩa như sau:

- **--class-path**: thư mục hoặc đầu vào chứa class files và resources cần đóng gói.
- **--module-version**: phiên bản module được ghi vào metadata của module.
- **--target-platform**: khai báo nền tảng đích cho JMOD có nội dung phụ thuộc nền tảng. Giá trị này không biên dịch lại native code và không thực hiện cross-compilation.
- **--date**: đặt timestamp ổn định cho các entry thay vì để thời điểm chạy build quyết định timestamp. Hãy dùng một giá trị ISO-8601 cố định theo chính sách release, chẳng hạn timestamp của commit phát hành.

Tùy chọn **--date** có ở các JDK hiện đại nhưng không có trong mọi phiên bản JDK cũ. Vì vậy phải xác nhận **jmod --help** của toolchain đã khóa và không giả định JDK 9 ban đầu hỗ trợ tùy chọn này. Khi cần byte-for-byte reproducibility, không được bỏ qua timestamp hoặc để mỗi lần build tự lấy thời gian hiện tại.

JMOD có thể nhận thêm các nhóm đầu vào khi module thực sự cần chúng:

~~~bash
jmod create --class-path build/classes --cmds build/staging/cmds --config build/staging/config --header-files build/staging/include --libs build/staging/lib --legal-notices build/staging/legal --man-pages build/staging/man --module-version 1.0.0 --target-platform linux-x64 --date 2025-01-01T00:00:00Z build/jmods/com.example.native.jmod
~~~

Không cần tạo các thư mục rỗng hoặc truyền mọi tùy chọn cho mọi module. Chỉ khai báo những nhóm nội dung có thật và đã được kiểm kê. Nếu module có main class, có thể khai báo **--main-class** theo thiết kế module; nếu không, không thêm metadata không cần thiết.

Giá trị **--date** phải giống nhau giữa các lần build có cùng đầu vào. Đồng thời, phải giữ ổn định thứ tự và tên đường dẫn đầu vào, nội dung class files, resource được sinh và phiên bản công cụ. Chuẩn hóa timestamp chỉ giải quyết một nguồn biến động; nó không tự bảo đảm toàn bộ JMOD sẽ giống byte.

## 7. Kiểm tra JMOD sau khi tạo

Không coi việc lệnh **jmod create** trả về thành công là bằng chứng đầy đủ rằng artifact đúng. Chạy các bước kiểm tra sau:

~~~bash
jmod describe build/jmods/com.example.greetings.jmod
jmod list build/jmods/com.example.greetings.jmod
jmod extract --dir build/verify/extracted build/jmods/com.example.greetings.jmod
~~~

Dùng kết quả để xác nhận:

- Tên module và module version đúng với release.
- Module descriptor thể hiện đúng các dependency, exported package, service và main class đã thiết kế.
- Danh sách entry chỉ chứa tệp được duyệt.
- Class files, resources, native files và metadata có mặt ở đúng vị trí.
- Không có tệp nhạy cảm, file tạm hoặc output ngoài phạm vi.

Sau khi kiểm tra cấu trúc, tính SHA-256 của JMOD và lưu kết quả cạnh artifact trong provenance record:

~~~bash
sha256sum build/jmods/com.example.greetings.jmod
~~~

Trên PowerShell có thể dùng:

~~~powershell
Get-FileHash .\build\jmods\com.example.greetings.jmod -Algorithm SHA256
~~~

Checksum của JMOD xác nhận tính toàn vẹn của chính tệp đã tạo. Nó không chứng minh nguồn gốc đáng tin cậy nếu manifest và checksum được lưu ở cùng một nơi có thể bị thay thế. Với pipeline phát hành, hãy lưu provenance và checksum trong hệ thống artifact có kiểm soát truy cập; ký hoặc attestation theo cơ chế bảo mật của tổ chức khi cần xác minh danh tính bên phát hành.

## 8. Kiểm tra khả năng liên kết bằng jlink

Đưa JMOD và các module phụ thuộc cần thiết lên module path của jlink. Ví dụ trên shell kiểu Unix:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:build/jmods" --add-modules com.example.greetings --output build/runtime
~~~

Trên Windows, dấu phân cách các phần tử của module path là dấu chấm phẩy (**;**); hãy điều chỉnh theo shell đang sử dụng.

jlink giải quyết module graph từ những module có trên module path. Nó không tự lấy dependency từ repository và cũng không làm cho các dependency bị thiếu xuất hiện trong JMOD. Nếu liên kết thất bại, kiểm tra module path, tên module, module descriptor và các dependency đã khóa.

Sau khi tạo runtime image, chạy kiểm thử smoke test trên nền tảng đích. Với module có native library, kiểm thử trên đúng OS và kiến trúc mà artifact khai báo.

## 9. Chứng minh khả năng tái tạo

Một lần build thành công chỉ chứng minh quy trình có thể tạo artifact. Muốn chứng minh khả năng tái tạo, hãy thực hiện hai lần build độc lập:

1. Checkout cùng commit vào hai workspace sạch.
2. Dùng cùng JDK, build tool, dependency lock, repository và cấu hình môi trường.
3. Tạo staging directory mới ở mỗi workspace.
4. Dùng cùng tham số jmod, bao gồm cùng **--date** và **--target-platform** khi có.
5. Tạo JMOD, kiểm tra bằng **jmod describe** và **jmod list**.
6. Tính SHA-256 của hai JMOD và so sánh.

Nếu SHA-256 giống nhau, hai tệp JMOD giống nhau ở mức byte. Nếu checksum khác, không kết luận ngay rằng nội dung module sai hoặc đúng. Trước hết hãy so sánh danh sách entry và module descriptor; sau đó giải nén vào hai thư mục sạch và so sánh từng tệp.

Khi nội dung sau giải nén giống nhau nhưng checksum JMOD khác, kiểm tra metadata đóng gói như timestamp và thứ tự entry, cùng phiên bản công cụ tạo gói. Khi class files hoặc resources khác nhau, quay lại kiểm tra compiler, dependency, generated source, locale, timezone, dữ liệu ngoài và trạng thái staging. Mỗi sai khác phải được truy về một đầu vào hoặc bước build cụ thể.

## 10. Provenance manifest và lưu trữ

Lưu một manifest bên cạnh JMOD, không phụ thuộc vào nội dung tự khai báo bên trong artifact. Manifest nên ghi:

- Tên module, module version, tên tệp JMOD và target platform.
- Commit mã nguồn, trạng thái working tree và danh sách submodule.
- Nhà cung cấp, phiên bản, build number, kiến trúc và checksum của JDK.
- Phiên bản build tool, wrapper, plugin và cấu hình repository.
- Tọa độ, phiên bản và checksum của dependency.
- Danh sách input file, đường dẫn tương đối và SHA-256 của từng tệp.
- Tham số jmod thực tế, bao gồm giá trị **--date**.
- Kết quả **jmod describe**, **jmod list**, kết quả kiểm thử và SHA-256 cuối cùng của JMOD.
- Thông tin job CI và thời điểm phát hành theo quy ước của tổ chức.

Manifest phải được tạo từ dữ liệu build thực tế, không nhập tay từ trí nhớ. Không đưa token, password, private key hoặc credential vào manifest, staging hay JMOD. Nếu manifest thay đổi, hãy lưu lại phiên bản mới cùng liên kết tới artifact tương ứng để có thể truy vết.

Lưu JMOD, manifest và log trong cùng một bản phát hành bất biến. Không ghi đè artifact đã phát hành bằng một tệp khác có cùng tên; tạo version hoặc build identifier mới để giữ được lịch sử và khả năng đối chiếu.

## 11. Quy trình CI đề xuất

Một pipeline có thể được chia thành các bước tuần tự:

1. **Checkout:** lấy đúng commit và kiểm tra trạng thái source.
2. **Resolve dependencies:** dùng lockfile và checksum verification.
3. **Prepare toolchain:** chọn JDK đã khóa, xác nhận phiên bản của **javac**, **jmod** và **jlink**.
4. **Compile:** biên dịch module và resources từ đầu vào đã xác định.
5. **Stage:** tạo staging directory sạch, kiểm kê tệp và tính checksum đầu vào.
6. **Package:** chạy **jmod create** với tham số đã lưu, đặc biệt là timestamp ổn định.
7. **Inspect:** chạy **jmod describe**, **jmod list** và kiểm tra các entry.
8. **Link and test:** chạy jlink cùng bộ module phụ thuộc và smoke test runtime image.
9. **Compare:** nếu pipeline kiểm tra reproducibility, build độc lập lần thứ hai và so sánh SHA-256.
10. **Publish:** lưu JMOD, manifest, checksum và log dưới cùng release identity.

Nếu một bước thất bại, pipeline phải giữ lại log và danh sách đầu vào đủ để điều tra. Không phát hành một JMOD được tạo từ staging chưa kiểm tra hoặc từ dependency chưa xác minh.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| **jmod describe** báo module không hợp lệ hoặc không đọc được descriptor | Thiếu **module-info.class**, descriptor không khớp hoặc dùng sai toolchain | Kiểm tra bước biên dịch và nội dung staging; tạo lại bằng JDK đã khóa |
| jlink báo không tìm thấy module | Module path thiếu JMOD hoặc dependency | Bổ sung đúng module vào module path và kiểm tra tên module |
| Hai JMOD có checksum khác | Timestamp, toolchain, thứ tự entry, class files hoặc resources khác nhau | So sánh metadata, giải nén và đối chiếu từng entry |
| JMOD chứa tệp không mong muốn | Staging tái sử dụng từ lần build trước hoặc đóng gói cả thư mục output | Xóa staging trong workspace build sạch và chỉ sao chép tệp đã khai báo |
| Native module chạy lỗi trên máy đích | Native binary không đúng OS/CPU hoặc thiếu thư viện hệ thống | Kiểm tra target platform và build native artifact trên môi trường tương thích |
| Build máy cá nhân thành công nhưng CI thất bại | JDK, dependency, environment hoặc đường dẫn không được khóa | Chuẩn hóa toolchain, lockfile, biến môi trường và script build |

## 13. Checklist trước khi phát hành

- [ ] Source commit, submodule và generated source đã được xác định.
- [ ] Dependency và build tool đã khóa phiên bản; checksum đầu vào đã được xác minh.
- [ ] JDK, **javac**, **jmod** và **jlink** thuộc cùng toolchain đã chọn.
- [ ] Staging directory được tạo mới và chỉ chứa các tệp được duyệt.
- [ ] Module descriptor, class files, resources và native inputs đúng với module.
- [ ] **jmod create** dùng tham số ổn định; **--date** được cố định nếu toolchain hỗ trợ.
- [ ] **jmod describe** và **jmod list** cho kết quả đúng.
- [ ] JMOD đã được kiểm tra checksum và lưu provenance manifest.
- [ ] jlink tạo được runtime image với các module phụ thuộc cần thiết.
- [ ] Kiểm thử trên nền tảng đích đã đạt.
- [ ] Hai lần build độc lập đã được so sánh nếu release yêu cầu byte-for-byte reproducibility.

## 14. Nguyên tắc cần nhớ

Tính tái tạo bắt đầu từ việc kiểm soát đầu vào, không bắt đầu ở lệnh đóng gói. JMOD chỉ có thể tái tạo ổn định khi mã nguồn, dependency, toolchain, staging, tham số và môi trường đều được ghi nhận và khóa. **--date** giúp loại bỏ biến động timestamp trên JDK hiện đại, còn checksum, kiểm tra entry và build độc lập cung cấp bằng chứng rằng artifact thực sự có thể được tạo lại.

Hãy coi JMOD là đầu vào có provenance cho bước liên kết bằng jlink. Giữ manifest và checksum bên cạnh artifact, kiểm tra module graph trên module path và dùng JDK đang được duy trì. Cách làm này giúp nhóm phát triển truy vết được từng tệp đầu vào, giải thích được sai khác giữa các lần build và phát hành runtime image một cách có kiểm soát.
