# Chạy cùng lệnh kiểm tra cục bộ và trên runner sạch

## Mục tiêu thực hành

Sau bài này, bạn có thể:

- Chọn một lệnh kiểm tra chuẩn cho dự án và chạy lệnh đó từ máy cá nhân.
- Cấu hình pipeline để runner sạch thực hiện đúng tập tác vụ kiểm tra ấy.
- Đồng bộ phiên bản JDK, công cụ build và đầu vào cần thiết giữa hai môi trường.
- Phân tích trường hợp máy cá nhân chạy thành công nhưng CI thất bại, hoặc ngược lại.

Bài thực hành dùng dự án Java xây dựng bằng Gradle làm ví dụ. Nguyên tắc áp dụng tương tự với Maven hoặc công cụ build khác: dự án phải cung cấp một điểm vào kiểm tra có thể gọi từ dòng lệnh, còn pipeline chỉ chuẩn bị môi trường rồi gọi điểm vào đó.

## Vì sao cần cùng một lệnh kiểm tra?

Một thay đổi thường được kiểm tra ở nhiều nơi: trên máy của lập trình viên, trong pull request và trước khi tạo artifact. Nếu mỗi nơi chạy một tập lệnh khác nhau, kết quả dễ mâu thuẫn. Máy cá nhân có thể chỉ chạy một nhóm test trong IDE, trong khi CI chạy thêm kiểm tra định dạng, phân tích tĩnh hoặc đóng gói. Khi CI phát hiện lỗi, nhóm khó biết lỗi đến từ mã nguồn hay do hai nơi đang kiểm tra những điều khác nhau.

Ta chọn một lệnh chuẩn, lưu cách build trong repository và dùng cùng tập tác vụ ở mọi nơi. Với dự án Gradle có Java plugin, ví dụ:

~~~bash
./gradlew --no-daemon clean check
~~~

**gradlew** là Gradle Wrapper đi kèm dự án. Wrapper chọn phiên bản Gradle được khai báo trong **gradle/wrapper/gradle-wrapper.properties**; người chạy không cần cài một bản Gradle toàn cục phù hợp. **clean** xóa đầu ra build cũ trong workspace. **check** gọi nhóm tác vụ kiểm tra mà dự án và các plugin đã cấu hình, thường bao gồm kiểm thử tự động và những bước xác minh khác.

Trên Windows PowerShell, dùng launcher tương ứng:

~~~powershell
.\gradlew.bat --no-daemon clean check
~~~

Tên launcher khác nhau theo hệ điều hành, nhưng cả hai lệnh đều gọi cùng Gradle Wrapper, cùng phiên bản Gradle và cùng tập tác vụ **clean check**. Nếu nhóm muốn có một lệnh ngắn, ổn định hơn, có thể tạo script **verify** của dự án để gọi Wrapper; script đó phải được dùng ở cả máy cá nhân lẫn CI.

Không lấy nút Build hoặc một cấu hình chạy riêng trong IDE làm cổng kiểm tra chuẩn. IDE vẫn hữu ích để chạy nhanh một test trong lúc phát triển, nhưng kết quả trước khi gửi thay đổi cần đến từ lệnh của repository.

## Chuẩn bị dự án

Trước khi chạy, kiểm tra repository có các thành phần cần thiết:

| Thành phần | Vai trò |
|---|---|
| gradlew và gradlew.bat | Launcher cho Linux/macOS và Windows |
| gradle/wrapper/gradle-wrapper.jar | Thành phần thực thi Wrapper |
| gradle/wrapper/gradle-wrapper.properties | Khai báo phiên bản Gradle phân phối |
| build.gradle hoặc build.gradle.kts | Khai báo plugin, dependency và tác vụ build/kiểm tra |
| settings.gradle hoặc settings.gradle.kts | Khai báo cấu trúc project và module |

Các file Wrapper phải được commit cùng mã nguồn. Không yêu cầu thành viên cài Gradle toàn cục hoặc tự chọn phiên bản Gradle theo ý mình. Với repository dùng Java, nhóm cũng cần thống nhất phiên bản JDK. Ví dụ trong bài này là JDK 21; nếu dự án quy định phiên bản khác, hãy thay con số trong cấu hình CI và cấu hình toolchain của dự án để chúng khớp nhau.

Trước khi chạy lần đầu, mở terminal tại thư mục gốc repository. Kiểm tra phiên bản Java và phiên bản mà Wrapper sử dụng:

~~~bash
java -version
./gradlew --version
~~~

Trên Windows, thay **./gradlew** bằng **.\gradlew.bat**. Kết quả giúp xác nhận máy đang dùng đúng JDK và Wrapper. Nếu build khai báo Java toolchain, hãy bảo đảm toolchain đó cũng có thể được cài hoặc tìm thấy trong môi trường chạy.

## Thực hành 1: chạy cổng kiểm tra trên máy cá nhân

1. Lấy mã nguồn và chuyển vào thư mục gốc của repository.
2. Xác nhận thay đổi cần kiểm tra đã nằm trong working tree. Nếu muốn đối chiếu chính xác với CI, hãy commit thay đổi hoặc ghi lại commit SHA sẽ được đẩy lên.
3. Chạy lệnh chuẩn:

   ~~~bash
   ./gradlew --no-daemon clean check
   ~~~

4. Chờ toàn bộ tác vụ kết thúc. Build chỉ được xem là đạt khi tiến trình trả mã thoát **0** và Gradle báo **BUILD SUCCESSFUL**. Nếu có tác vụ thất bại, đọc tên tác vụ và thông báo lỗi trước khi sửa mã.
5. Chạy lại lệnh sau khi sửa. Vì có **clean**, kết quả không phụ thuộc vào các file đầu ra còn sót lại từ lần build trước.

**--no-daemon** yêu cầu Gradle không tái sử dụng daemon nền lâu dài giữa các lần gọi. Gradle vẫn có thể tạo tiến trình daemon dùng một lần trong một số cấu hình JVM; mục đích ở đây là giảm khác biệt do trạng thái daemon tồn tại từ phiên làm việc trước.

Lưu ý: **clean** chỉ xóa đầu ra build của project. Nó không xóa JDK, biến môi trường, dependency cache trong thư mục Gradle của người dùng, dịch vụ đang chạy hoặc file chưa được Git theo dõi. Vì vậy, lệnh này tạo một lần build sạch trong workspace, nhưng chưa tự chứng minh rằng project có thể build trên một máy hoàn toàn mới.

## Thực hành 2: chạy đúng cổng kiểm tra trên runner sạch

Runner là máy hoặc môi trường thực thi job CI. Runner sạch cần checkout mã nguồn của commit đang được kiểm tra, cài đúng JDK, rồi gọi Wrapper từ thư mục gốc. Ví dụ workflow GitHub Actions tối thiểu:

~~~yaml
name: Verify

on:
  push:
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Run the project verification command
        run: ./gradlew --no-daemon clean check
~~~

Phiên bản JDK trong ví dụ phải khớp với yêu cầu thực tế của dự án. Khi áp dụng vào repository thật, hãy tuân thủ chính sách pin phiên bản action của tổ chức.

Workflow thực hiện ba việc rõ ràng: lấy đúng commit, chuẩn bị JDK và gọi lệnh kiểm tra của repository. Runner Linux sử dụng **./gradlew**; máy Windows sử dụng **gradlew.bat**. Tập tác vụ **clean check** vẫn giống nhau. Không viết lại danh sách test hoặc lệnh build riêng trong workflow, vì như vậy quy tắc kiểm tra sẽ bị phân tán giữa mã nguồn và pipeline.

Runner sạch giúp phát hiện những phụ thuộc vô tình vào máy cá nhân: file chưa commit, thư mục build cũ, cấu hình IDE, biến môi trường chỉ có trên một máy hoặc phần mềm cài thủ công. Trên runner được cấp mới cho job, workspace bắt đầu từ checkout của commit. Nếu CI có khôi phục cache, workspace vẫn có thể sạch nhưng cache của công cụ hoặc dependency được dùng lại; hai khái niệm này cần được phân biệt.

Ở lần thiết lập đầu tiên, hãy chạy pipeline mà chưa thêm cache build tùy chỉnh. Sau khi luồng cơ bản chạy ổn định, có thể thêm cache dependency để giảm thời gian tải. Cache chỉ là tối ưu hiệu năng: khi điều tra lỗi khó tái hiện, thử chạy lại không khôi phục cache hoặc dùng khóa cache mới. Không để kết quả đúng phụ thuộc vào một thư mục đầu ra được cache từ job trước.

## Đối chiếu hai môi trường

Để so sánh có ý nghĩa, máy cá nhân và runner cần nhận cùng đầu vào. Dùng bảng sau khi một lần chạy cho kết quả khác nhau:

| Yếu tố | Máy cá nhân | Runner CI |
|---|---|---|
| Mã nguồn | Commit hoặc working tree đang kiểm tra | Checkout đúng commit SHA |
| Java | JDK và toolchain theo yêu cầu dự án | Cùng major version JDK/toolchain |
| Công cụ build | Gradle Wrapper trong repository | Cùng Wrapper và file cấu hình |
| Tác vụ | clean check | clean check |
| Thư mục chạy | Gốc repository | Gốc repository |
| Cấu hình | Biến môi trường và tham số đã khai báo | Khai báo tương ứng trong job |
| Trạng thái workspace | Có thể chứa file chưa commit | Checkout sạch của commit |

Không cần mọi máy có cùng hệ điều hành, nhưng khác biệt hệ điều hành có thể làm lộ lỗi về đường dẫn, chữ hoa/chữ thường, quyền thực thi hoặc script shell. Nếu dự án hỗ trợ nhiều hệ điều hành, hãy bổ sung job kiểm tra trên các hệ điều hành đó thay vì giả định một runner Linux chứng minh được tất cả.

Với thông tin bí mật như token truy cập dịch vụ kiểm thử, dùng kho secrets của CI và cấu hình môi trường tương ứng khi chạy local. Không commit secret vào repository, không in secret ra log và không tạo một giá trị giả khiến test vô tình bỏ qua nhánh xác thực. Nếu kiểm thử không cần dịch vụ bên ngoài, ưu tiên fixture hoặc dịch vụ giả có thể khởi tạo lặp lại.

## Khi kết quả local và CI khác nhau

Trước hết, ghi lại commit SHA, lệnh đã chạy, phiên bản Java, phiên bản Gradle và tác vụ thất bại. Có thể lấy thông tin bằng:

~~~bash
git rev-parse HEAD
java -version
./gradlew --version
~~~

Sau đó phân loại tình huống:

| Kết quả | Hướng điều tra |
|---|---|
| Local thất bại, CI thất bại | Ưu tiên sửa lỗi mã nguồn, test hoặc cấu hình build; xem tác vụ đầu tiên thất bại. |
| Local thành công, CI thất bại | So sánh commit, JDK, toolchain, biến môi trường, quyền file, hệ điều hành và file chưa commit. Thử clone mới hoặc worktree sạch ở local. |
| Local thất bại, CI thành công | Kiểm tra JDK cục bộ, cấu hình cá nhân, cache cũ và biến môi trường. Xác nhận local đang kiểm tra đúng commit. |
| Cả hai lúc đạt lúc trượt | Tìm test phụ thuộc thời gian, thứ tự chạy, cổng mạng, dữ liệu dùng chung hoặc dịch vụ bên ngoài. Làm test độc lập và dữ liệu đầu vào xác định. |

Khi cần thêm dấu vết, chạy lại cùng tác vụ với **--stacktrace** để xem stack trace:

~~~bash
./gradlew --no-daemon clean check --stacktrace
~~~

Giữ nguyên tập tác vụ khi chẩn đoán để kết quả có thể so sánh. Tránh sửa workflow thành một chuỗi lệnh khác chỉ để làm CI xanh tạm thời; nếu phát hiện dự án thiếu một bước kiểm tra cần thiết, hãy đưa bước đó vào cấu hình build chuẩn rồi để local và CI cùng gọi lại cổng kiểm tra.

## Bài tập tự thực hiện

1. Chọn một repository Java có Gradle Wrapper và xác định phiên bản JDK mà dự án yêu cầu.
2. Chạy **./gradlew --no-daemon clean check** tại máy cá nhân (hoặc lệnh launcher tương ứng trên Windows). Ghi lại commit SHA và kết quả.
3. Tạo workflow CI có bước checkout, thiết lập cùng JDK và chạy chính lệnh kiểm tra đó.
4. Đẩy một thay đổi có test đi kèm. Mở pull request và xác nhận job kiểm tra chạy trên commit tương ứng.
5. Tạm thời tạo một lỗi có thể phát hiện bằng test, chạy local và quan sát CI thất bại. Sau đó sửa lỗi, chạy lại local và xác nhận CI chuyển sang thành công.
6. Nếu local và CI cho kết quả khác nhau, dùng bảng đối chiếu phía trên để tìm khác biệt và ghi lại nguyên nhân.

## Tiêu chí hoàn thành

- [ ] Repository có Gradle Wrapper và cấu hình phiên bản công cụ được commit.
- [ ] Máy cá nhân chạy được clean check bằng Wrapper từ thư mục gốc.
- [ ] Runner checkout đúng commit và thiết lập đúng JDK.
- [ ] Pipeline gọi cùng tập tác vụ clean check như máy cá nhân.
- [ ] Job thất bại khi kiểm tra thất bại và thành công khi toàn bộ kiểm tra đạt.
- [ ] Có thể giải thích ít nhất hai nguyên nhân khiến local và runner cho kết quả khác nhau.

Khi hoàn tất, nhóm có một cổng kiểm tra có thể lặp lại và truy vết được từ commit đến kết quả CI. Đây là nền tảng để các bước sau quản lý artifact, triển khai môi trường và đặt quality gate dựa trên kết quả kiểm tra đáng tin cậy.
