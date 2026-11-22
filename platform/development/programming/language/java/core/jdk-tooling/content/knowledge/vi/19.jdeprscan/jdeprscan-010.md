# Kế hoạch thay thế API deprecated trong Java

Khi một API Java bị đánh dấu **deprecated**, nhóm phát triển cần quyết định cách và thời điểm thay thế nó. Việc thay thế không nên chỉ là đổi tên phương thức: API mới có thể khác về ngữ nghĩa, múi giờ, cách xử lý null, ngoại lệ, bảo mật, hiệu năng hoặc khả năng tương thích.

**jdeprscan** hỗ trợ bước kiểm kê bằng cách quét class file, thư mục class và JAR để tìm tham chiếu đến API deprecated của Java. Kết quả quét là đầu vào cho kế hoạch migration. Công cụ không tự đề xuất API thay thế, không sửa mã nguồn và không chứng minh rằng ứng dụng đã an toàn sau khi migration.

Một kế hoạch tốt xác định rõ API nào đang được dùng, mức độ khẩn cấp, lựa chọn thay thế, khác biệt hành vi, phạm vi kiểm thử, người phụ trách và tiêu chí hoàn thành.

## 1. Vì sao cần lập kế hoạch thay thế API?

API được đánh dấu deprecated khi nhà phát triển nền tảng không còn khuyến nghị sử dụng nó. Lý do có thể là:

- API có thiết kế cũ hoặc khó sử dụng an toàn.
- Có API mới rõ ràng hơn hoặc hỗ trợ nhiều trường hợp hơn.
- Cách triển khai cũ gây rủi ro bảo mật hoặc khó bảo trì.
- API không còn phù hợp với kiến trúc hiện tại.
- Nền tảng dự kiến loại bỏ API trong một bản phát hành tương lai.

Deprecated không đồng nghĩa với đã bị xóa. Một API deprecated có thể vẫn hoạt động trong nhiều phiên bản, nhưng việc tiếp tục phụ thuộc vào nó làm tăng chi phí nâng cấp và rủi ro tương thích.

Đặc biệt cần chú ý annotation:

~~~java
@Deprecated(since = "17", forRemoval = true)
public void oldOperation() {
}
~~~

- **since** cho biết phiên bản API được đánh dấu deprecated, nếu metadata có khai báo.
- **forRemoval = true** cho biết API được dự định loại bỏ trong tương lai.
- **forRemoval = false** hoặc không chỉ định thuộc tính này có nghĩa API deprecated nhưng chưa được đánh dấu để loại bỏ.

forRemoval=true là tín hiệu ưu tiên cao, không phải cam kết rằng API chắc chắn bị xóa ở phiên bản kế tiếp. Hãy kiểm tra tài liệu và release notes của JDK mục tiêu.

## 2. Vai trò của jdeprscan trong migration

jdeprscan là công cụ phân tích bytecode đi kèm JDK. Công cụ tìm tham chiếu đến deprecated APIs trong các class, thư mục class hoặc JAR.

Có thể quét:

- Một class file.
- Một thư mục là gốc của package hierarchy.
- Một JAR.
- Một class name đầy đủ.
- Nhiều đầu vào trong cùng một lần chạy.

jdeprscan so sánh các tham chiếu được tìm thấy với tập API deprecated của Java release được chọn. Vì vậy, cần xác định phiên bản Java mục tiêu trước khi quét.

### Những gì jdeprscan giúp trả lời

- Artifact nào đang gọi API deprecated?
- Class nào trong artifact chứa tham chiếu đó?
- API nào đã deprecated trong release mục tiêu?
- API nào được đánh dấu for removal?
- Sau migration, những tham chiếu nào vẫn còn?

### Những gì jdeprscan không làm

- Không tự tìm API thay thế tốt nhất.
- Không sửa source code hoặc bytecode.
- Không đánh giá API thay thế có giữ nguyên nghiệp vụ hay không.
- Không đảm bảo phát hiện mọi lời gọi được tạo động bằng reflection hoặc cấu hình runtime.
- Không thay thế kiểm tra API deprecated của thư viện bên thứ ba.
- Không thay thế compile, unit test, integration test và kiểm thử trên JDK mục tiêu.

Do đó, hãy kết hợp jdeprscan với compiler warnings, tài liệu API, review mã và test.

## 3. Bước đầu: xác định release mục tiêu

Trước khi quét, xác định ứng dụng sẽ chạy trên Java release nào. Release mục tiêu quyết định tập API deprecated mà jdeprscan sử dụng để đánh giá.

Ví dụ, nếu ứng dụng phải tiếp tục tương thích với Java 17:

~~~bash
jdeprscan --release 17 build/app.jar
~~~

Nếu mục tiêu là Java 24:

~~~bash
jdeprscan --release 24 build/app.jar
~~~

Dùng release phù hợp với runtime mà nhóm đang chuẩn bị hỗ trợ. Không chọn release chỉ vì đó là JDK đang cài trên máy developer nếu sản phẩm phải chạy trên một phiên bản khác.

Cũng cần ghi lại:

- JDK vendor và version dùng để build.
- Java release mà ứng dụng hỗ trợ.
- Phiên bản thư viện phụ thuộc.
- Hệ điều hành và kiến trúc triển khai.
- Các module hoặc profile build có thể tạo ra artifact khác nhau.

Khi sản phẩm hỗ trợ nhiều Java release, hãy lập ma trận quét theo từng release cần hỗ trợ.

## 4. Kiểm kê deprecated APIs bằng jdeprscan

### Xem danh sách API deprecated

Liệt kê các API deprecated của release:

~~~bash
jdeprscan --list --release 24
~~~

Chỉ liệt kê API được đánh dấu for removal:

~~~bash
jdeprscan --list --release 24 --for-removal
~~~

Tùy chọn --list chỉ in danh sách API; không thực hiện scan. Không truyền thêm JAR, class hoặc directory khi dùng chế độ này.

### Quét một JAR

~~~bash
jdeprscan --release 24 build/app.jar
~~~

### Quét thư mục class

~~~bash
jdeprscan --release 24 build/classes
~~~

Thư mục được truyền vào là gốc của package hierarchy đã biên dịch.

### Quét một class file

~~~bash
jdeprscan --release 24 build/classes/com/example/LegacyAdapter.class
~~~

### Quét nhiều artifact

~~~bash
jdeprscan --release 24 build/app.jar build/plugins build/legacy-helper.jar
~~~

Quét tất cả artifact liên quan giúp tìm usage trong mã ứng dụng và các thư viện được đóng gói riêng. Hãy giữ danh sách artifact đã quét để có thể lặp lại cùng quy trình trong lần nâng cấp tiếp theo.

### Cung cấp class path để resolve dependency

Nếu cần tìm class phụ thuộc khi phân tích, truyền class path:

~~~bash
jdeprscan --release 24 --class-path "lib/*" build/app.jar
~~~

Trên Windows, wildcard cũng có thể được đặt trong dấu nháy:

~~~powershell
jdeprscan --release 24 --class-path "lib/*" build/app.jar
~~~

Dùng đúng thư viện cần thiết để resolve class. Nếu class path thiếu, kết quả có thể không đầy đủ hoặc công cụ phát ra cảnh báo.

### Chỉ quét API for removal

~~~bash
jdeprscan --release 24 --for-removal build/app.jar
~~~

Đây là cách ưu tiên tìm các tham chiếu có rủi ro cao hơn. Tuy nhiên, kết quả trống không có nghĩa ứng dụng không còn API deprecated; nó chỉ cho biết lần quét này không tìm thấy usage thuộc tập for-removal đã chọn.

### Tùy chọn hữu ích khác

| Tùy chọn | Mục đích |
|---|---|
| --release | Chọn Java SE release dùng làm tập API deprecated |
| --for-removal | Chỉ quét hoặc liệt kê API deprecated for removal |
| --class-path | Cung cấp đường dẫn tìm class phụ thuộc |
| --list | Liệt kê API deprecated, không quét artifact |
| --verbose | In thêm thông tin khi xử lý |
| --version | In version rút gọn của tool |
| --full-version | In đầy đủ version string |
| --help | Hiển thị cú pháp và tùy chọn |

Kiểm tra toolchain hiện tại:

~~~bash
jdeprscan --version
jdeprscan --help
~~~

Tập release mà công cụ hỗ trợ phụ thuộc phiên bản JDK đang cài. Dùng --help của đúng toolchain trong CI để xác nhận cú pháp.

## 5. Ưu tiên các finding

Không phải mọi finding đều có cùng mức khẩn cấp. Hãy phân loại trước khi lên lịch migration.

| Mức ưu tiên | Tình huống | Hành động |
|---|---|---|
| P0 — khẩn cấp | API deprecated for removal, đã có trong release mục tiêu hoặc có nguy cơ bị loại bỏ khi nâng cấp | Xác định phương án thay thế và lịch xử lý sớm |
| P1 — cao | API deprecated có replacement chính thức hoặc liên quan bảo mật, concurrency, serialization | Đưa vào kế hoạch migration gần nhất |
| P2 — trung bình | API deprecated nhưng chưa có thời điểm loại bỏ và vẫn hoạt động | Ghi nhận, ước lượng effort, theo dõi |
| P3 — cần điều tra | Finding thuộc thư viện bên thứ ba, mã generated, plugin hoặc đường chạy ít dùng | Xác định owner và cách xử lý trước khi kết luận |

Khi ưu tiên, xem xét thêm:

- Tần suất API được gọi trong luồng nghiệp vụ.
- Mức độ ảnh hưởng nếu API bị loại bỏ.
- Khả năng có replacement tương đương.
- Số module và service bị ảnh hưởng.
- Khả năng tương thích với phiên bản Java thấp nhất mà sản phẩm hỗ trợ.
- Effort và rủi ro của việc thay thế.
- Khả năng kiểm thử tự động và rollback.

Một API chỉ xuất hiện trong test hoặc công cụ build có thể có mức ưu tiên khác API được dùng trong luồng giao dịch chính. Tuy nhiên, không bỏ qua test và toolchain vì chúng cũng có thể ngừng hoạt động khi nâng cấp JDK.

## 6. Tạo inventory và kế hoạch thay thế

Mỗi finding nên trở thành một dòng trong migration inventory. Không chỉ lưu tên API; cần ghi cả vị trí sử dụng và quyết định thay thế.

Mẫu bảng theo dõi:

| Trường | Nội dung cần ghi |
|---|---|
| Artifact | JAR, module hoặc thư mục chứa class |
| Class / member | Class và method/field tham chiếu API |
| Deprecated API | Tên API đầy đủ và chữ ký |
| Deprecated since | Phiên bản đánh dấu deprecated nếu có |
| For removal | Có/không theo metadata |
| Target release | Java release dùng để đánh giá |
| Replacement | API hoặc thiết kế thay thế |
| Semantic difference | Khác biệt hành vi cần xử lý |
| Owner | Người hoặc nhóm phụ trách |
| Test plan | Unit, integration, compatibility và performance tests |
| Target milestone | Bản phát hành dự kiến |
| Status | Open, Investigating, Planned, In progress, Verified hoặc Accepted risk |

Ví dụ một dòng inventory:

| Artifact | Deprecated API | Replacement dự kiến | Rủi ro cần xác minh |
|---|---|---|---|
| legacy-report.jar | java.util.Date.getYear() | java.time.LocalDate tại ZoneId xác định | Múi giờ và cách tính năm |
| security-adapter.jar | API security cũ | API bảo mật được tài liệu JDK khuyến nghị | Quyền, provider và hành vi xác thực |

Replacement trong bảng là phương án cần nghiên cứu, không phải quyết định tự động. Hãy xác nhận bằng Javadoc, migration guide, release notes và test thực tế.

## 7. Tìm replacement và đánh giá khác biệt ngữ nghĩa

Với từng API deprecated:

1. Mở Javadoc của API cũ và đọc phần deprecated note.
2. Theo liên kết replacement được tài liệu chính thức đề xuất.
3. Kiểm tra release notes, migration guide hoặc JEP liên quan.
4. Xác định replacement có tồn tại trong Java release thấp nhất mà sản phẩm hỗ trợ hay không.
5. So sánh chữ ký, kiểu dữ liệu, ngoại lệ, giá trị mặc định và vòng đời tài nguyên.
6. Xác định thay đổi nào cần cập nhật ở caller, cấu hình, persistence hoặc giao thức.
7. Tạo thử nghiệm chứng minh hành vi cũ và mới đáp ứng cùng hợp đồng nghiệp vụ.

Không phải API deprecated nào cũng có replacement một-một. Đôi khi replacement là một nhóm lớp, một mô hình dữ liệu mới hoặc một quy trình khác. Khi đó, cần lập thiết kế migration thay vì thay tên phương thức.

### Những khác biệt cần kiểm tra

- **Giá trị và đơn vị:** năm có thể tính từ mốc khác, thời lượng có thể dùng millisecond hoặc Duration.
- **Múi giờ và locale:** kết quả ngày/giờ có thể thay đổi theo ZoneId hoặc Locale.
- **Nullability:** replacement có thể từ chối null hoặc trả Optional.
- **Ngoại lệ:** API mới có thể ném checked exception hoặc runtime exception khác.
- **Thread safety:** lớp mới có thể mutable hoặc immutable khác lớp cũ.
- **Resource lifecycle:** API mới có thể yêu cầu close hoặc quản lý resource rõ ràng.
- **Encoding:** charset mặc định có thể khác; nên chỉ định charset rõ ràng.
- **Security:** quyền, provider, algorithm hoặc default policy có thể thay đổi.
- **Serialization:** serialized form có thể không tương thích.
- **Performance:** cách cấp phát, caching hoặc độ phức tạp có thể khác.

## 8. Ví dụ migration: Date.getYear() sang java.time

Một ví dụ kinh điển là phương thức Date.getYear(). Phương thức này đã deprecated từ lâu và trả về năm trừ đi 1900. Với Java hiện đại, nên chuyển sang java.time và xác định múi giờ rõ ràng.

### Cách cũ

~~~java
@SuppressWarnings("deprecation")
static int legacyYear(Date date) {
    return date.getYear() + 1900;
}
~~~

Giá trị Date.getYear() được diễn giải theo múi giờ mặc định của môi trường. Kết quả là một số năm theo lịch địa phương, không phải trực tiếp là năm UTC.

### Cách mới

~~~java
static int migratedYear(Date date, ZoneId zone) {
    return date.toInstant()
            .atZone(zone)
            .getYear();
}
~~~

Cách mới chuyển instant sang thời gian địa phương tại ZoneId được chỉ định rồi lấy năm. Điều này buộc người thiết kế API phải quyết định múi giờ theo nghiệp vụ.

### Ví dụ Java 17+ chạy được

Tạo tệp src/com/example/ApiReplacementPlanDemo.java:

~~~java
package com.example;

import java.time.Instant;
import java.time.ZoneId;
import java.util.Date;

public class ApiReplacementPlanDemo {

    static int legacyYear(Date date) {
        return date.getYear() + 1900;
    }

    static int migratedYear(Date date, ZoneId zone) {
        return date.toInstant()
                .atZone(zone)
                .getYear();
    }

    public static void main(String[] args) {
        Date value = Date.from(
                Instant.parse("2024-12-31T23:30:00Z")
        );

        ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
        int year = migratedYear(value, businessZone);

        System.out.println("Migrated year: " + year);
    }
}
~~~

Biên dịch với Java 17:

~~~bash
javac --release 17 -Xlint:deprecation -d out src/com/example/ApiReplacementPlanDemo.java
~~~

Compiler phát cảnh báo deprecated tại lời gọi Date.getYear() trong phương thức legacyYear. Cảnh báo này được giữ lại trong ví dụ để cho thấy usage cũ vẫn tồn tại trong bytecode cần scan.

Chạy phần đã migration:

~~~bash
java -cp out com.example.ApiReplacementPlanDemo
~~~

Output:

~~~text
Migrated year: 2025
~~~

Ngày giờ đầu vào là 2024-12-31 23:30 UTC. Tại Asia/Ho_Chi_Minh, thời điểm đó là 2025-01-01 06:30, vì vậy năm địa phương là 2025.

### Quét bytecode của ví dụ

~~~bash
jdeprscan --release 17 out
~~~

jdeprscan sẽ tìm tham chiếu deprecated còn được lưu trong class file, bao gồm lời gọi Date.getYear() trong phương thức legacyYear. Diagnostic cụ thể có thể thay đổi theo JDK.

Có thể kiểm tra riêng API for removal:

~~~bash
jdeprscan --release 17 --for-removal out
~~~

Date.getYear() là deprecated nhưng không phải ví dụ for-removal, nên không xuất hiện trong tập lọc này. Điều đó minh họa vì sao cần chạy cả scan đầy đủ và scan for-removal.

### Quyết định migration cần ghi lại

- Nếu cần giữ hành vi cũ theo múi giờ mặc định, dùng ZoneId.systemDefault() và kiểm thử trên môi trường triển khai.
- Nếu nghiệp vụ phụ thuộc một múi giờ cụ thể, truyền ZoneId rõ ràng như Asia/Ho_Chi_Minh.
- Nếu dữ liệu là ngày lịch không đại diện một instant, cân nhắc lưu LocalDate thay vì Date.
- Không chỉ thay getYear() bằng LocalDate mà không xác định múi giờ; kết quả có thể lệch một năm gần ranh giới ngày đầu/cuối năm.

Ví dụ cho thấy thay API cần giữ đúng ý nghĩa dữ liệu, không chỉ làm compiler hết warning.

## 9. Thiết kế các giai đoạn migration

Với dự án lớn, thay thế API theo từng giai đoạn giúp giảm rủi ro và dễ kiểm soát tiến độ.

### Giai đoạn 1: Baseline

- Chốt target JDK và các release cần hỗ trợ.
- Quét toàn bộ JAR, thư mục class và module artifact.
- Chạy cả scan đầy đủ và scan --for-removal.
- Lưu kết quả cùng JDK vendor/version và commit source.
- Tạo inventory và phân loại P0/P1/P2/P3.

### Giai đoạn 2: Research và thiết kế

- Tra cứu replacement chính thức.
- So sánh ngữ nghĩa cũ/mới.
- Xác định dependency, caller và module bị ảnh hưởng.
- Quyết định dùng adapter, facade hoặc thay đổi trực tiếp.
- Ghi rõ các trường hợp không có replacement một-một.
- Chốt test plan và owner.

### Giai đoạn 3: Thay thế theo phạm vi nhỏ

- Chia migration theo API hoặc bounded context.
- Thay một nhóm usage có cùng ngữ nghĩa trong mỗi change.
- Tránh sửa đồng thời nhiều phần không liên quan.
- Nếu nhiều module dùng API cũ, cân nhắc một adapter chung để kiểm soát hành vi.
- Cập nhật tài liệu và ví dụ sử dụng API mới.

### Giai đoạn 4: Kiểm thử

- Unit test cho từng replacement.
- Integration test cho luồng gọi qua nhiều module.
- Regression test so sánh kết quả nghiệp vụ cũ/mới.
- Boundary test cho null, timezone, locale, overflow và dữ liệu cũ.
- Compatibility test với JDK thấp nhất được hỗ trợ.
- Performance test nếu thay đổi thuật toán hoặc cách quản lý resource.
- Kiểm tra serialization và persistence nếu cấu trúc dữ liệu thay đổi.

### Giai đoạn 5: Quét lại và xác nhận

- Build lại toàn bộ artifact.
- Chạy jdeprscan theo target release.
- Chạy riêng --for-removal để xác nhận không còn usage ưu tiên cao.
- Dùng javac -Xlint:deprecation và -Xlint:removal cho source code.
- Xem xét mọi finding còn lại và phân loại accepted risk có lý do.
- Xác nhận không có lỗi runtime hoặc regression.

### Giai đoạn 6: Phát hành và đóng migration

- Triển khai theo môi trường hoặc nhóm người dùng.
- Theo dõi exception, log, metrics và hành vi nghiệp vụ.
- Chuẩn bị rollback nếu replacement làm thay đổi hành vi không mong muốn.
- Cập nhật migration inventory và tài liệu vận hành.
- Đặt ngày xem xét lại cho các accepted risk.
- Chỉ đóng migration khi tiêu chí hoàn thành đã đạt.

## 10. Dùng compiler warnings cùng jdeprscan

jdeprscan kiểm tra bytecode đã biên dịch. Trong quá trình phát triển, compiler có thể phát hiện deprecated usage ngay khi biên dịch source.

~~~bash
javac --release 17 -Xlint:deprecation -Xlint:removal -d out src/com/example/*.java
~~~

Hai nhóm warning có ý nghĩa:

- **deprecation:** sử dụng API deprecated.
- **removal:** sử dụng API được đánh dấu deprecated for removal.

Trong JDK hiện đại, có thể bật các warning này trong build để phát hiện usage mới sớm hơn.

Khi codebase đã xử lý baseline cũ, có thể cân nhắc biến warning thành lỗi trong CI bằng tùy chọn compiler phù hợp. Chỉ bật chế độ nghiêm ngặt sau khi nhóm đã thống nhất cách xử lý warning hiện hữu; nếu không, build có thể thất bại vì hàng loạt finding cũ chưa được phân loại.

jdeprscan và javac bổ sung cho nhau:

| Công cụ | Thời điểm | Giá trị |
|---|---|---|
| javac -Xlint:deprecation | Khi compile source | Phát hiện usage mới ngay lúc phát triển |
| javac -Xlint:removal | Khi compile source | Làm nổi bật API có nguy cơ bị loại bỏ |
| jdeprscan | Sau khi có class/JAR | Scan artifact đã build, kể cả thư viện không có source |
| Review tài liệu API | Trong thiết kế migration | Tìm replacement và hiểu thay đổi ngữ nghĩa |
| Automated tests | Sau khi thay thế | Xác nhận hành vi và compatibility |

## 11. Migration thư viện bên thứ ba và mã generated

Finding trong JAR có thể đến từ dependency bên thứ ba, không phải source code của ứng dụng.

Với mỗi finding:

1. Xác định class thuộc artifact nào.
2. Kiểm tra phiên bản thư viện hiện tại.
3. Tìm phiên bản mới đã thay thế API deprecated chưa.
4. Đọc release notes và compatibility notes của thư viện.
5. Nâng cấp dependency trong một change có thể kiểm thử.
6. Nếu upstream chưa sửa, quyết định giữ tạm, thay thư viện, fork hoặc cô lập usage.

Không sửa trực tiếp bytecode của JAR bên thứ ba trừ khi quy trình phát hành có kiểm soát và được kiểm thử đầy đủ.

Mã generated cũng cần được phân loại riêng. Nếu generator cũ liên tục tạo ra usage deprecated, sửa template hoặc nâng phiên bản generator; chỉ sửa file generated có thể khiến lỗi quay lại ở lần build tiếp theo.

## 12. Những dependency động mà scan tĩnh có thể bỏ sót

jdeprscan đọc tham chiếu trong class file. Một số usage không xuất hiện rõ dưới dạng lời gọi tĩnh:

- Reflection dùng tên class hoặc method lấy từ cấu hình.
- Class được nạp bằng plugin hoặc ServiceLoader theo môi trường runtime.
- Tên API được tạo thành chuỗi ở runtime.
- Native code gọi JNI hoặc truy cập thành phần bên ngoài JVM.
- Mã được sinh hoặc nạp sau khi scan artifact.

Để kiểm tra những trường hợp này:

- Tìm chuỗi tên class/method trong cấu hình và resource.
- Kiểm tra plugin registry và ServiceLoader provider.
- Chạy integration test với các profile và plugin thực tế.
- Theo dõi log, telemetry và lỗi runtime.
- Đưa các dependency động đã biết vào migration inventory.

Không kết luận “không còn deprecated usage” chỉ từ một lần jdeprscan nếu hệ thống có cơ chế nạp động.

## 13. Tiêu chí hoàn thành migration

Một migration chỉ hoàn tất khi đáp ứng tiêu chí đã thống nhất, ví dụ:

- Tất cả artifact production đã được scan theo target release.
- Không còn usage for-removal chưa được chấp thuận.
- Usage deprecated còn lại có owner, lý do và ngày xem xét.
- Source compile không phát sinh warning mới ngoài baseline được chấp thuận.
- Unit và integration tests đạt.
- Các khác biệt ngữ nghĩa đã được xác nhận bằng test.
- Ứng dụng chạy trên JDK mục tiêu và các nền tảng được hỗ trợ.
- Hiệu năng, bảo mật và tương thích không suy giảm ngoài mức đã chấp nhận.
- Tài liệu và hướng dẫn nâng cấp đã cập nhật.
- Kết quả scan sau migration được lưu để so sánh với baseline.

Không nên chỉ đặt tiêu chí là “jdeprscan không in dòng nào”. Có thể có API deprecated được chấp nhận có chủ đích, dependency động ngoài phạm vi scan hoặc artifact chưa được quét. Tiêu chí cần phản ánh phạm vi thật của hệ thống.

## 14. Lỗi thường gặp khi lập kế hoạch thay thế API

### Thay API theo tên mà không so sánh ngữ nghĩa

Hai API có thể cùng tên hoặc cùng kiểu dữ liệu nhưng khác múi giờ, default value, ngoại lệ hoặc thread safety. Lập bảng semantic difference và test các trường hợp biên trước khi thay thế.

### Chỉ scan mã ứng dụng

Usage có thể nằm trong JAR, plugin hoặc thư viện đóng gói riêng. Scan mọi artifact được triển khai cùng ứng dụng và phân biệt finding của dependency bên thứ ba.

### Chỉ chạy --for-removal

Tùy chọn này bỏ qua API deprecated chưa được đánh dấu forRemoval. Chạy scan đầy đủ trước, sau đó chạy thêm scan ưu tiên removal.

### Chọn sai --release

Nếu quét theo JDK cài trên máy nhưng sản phẩm target release khác, báo cáo có thể không phản ánh đúng API mục tiêu. Ghi target release và dùng nó nhất quán trong CI.

### Xem finding là lỗi runtime ngay lập tức

Deprecated không có nghĩa API đã bị xóa. Hãy đánh giá mức ưu tiên, lịch hỗ trợ và compatibility thay vì thay đổi vội vàng.

### Không quét lại sau migration

Source có thể đã được sửa nhưng artifact cũ vẫn được đưa vào package. Build lại, scan lại artifact cuối cùng và lưu kết quả.

### Không kiểm tra reflection và plugin

Static scan không thể xác nhận mọi lời gọi động. Bổ sung tìm kiếm cấu hình và integration test trên các profile thực tế.

### Không có owner hoặc thời hạn

Finding không có người phụ trách thường bị bỏ quên. Mỗi finding cần owner, target milestone và trạng thái rõ ràng.

## 15. Checklist kế hoạch thay thế API

- Chốt target Java release và vendor JDK.
- Lưu baseline của source revision và danh sách artifact.
- Chạy jdeprscan đầy đủ trên JAR, class directory và plugin.
- Chạy thêm jdeprscan --for-removal.
- Xác định class, artifact và API signature của từng finding.
- Phân loại mức ưu tiên theo forRemoval, mức sử dụng và tác động.
- Tra cứu replacement trong Javadoc, migration guide và release notes.
- Ghi lại khác biệt ngữ nghĩa và rủi ro tương thích.
- Chỉ định owner, target milestone và test plan.
- Thay thế theo nhóm nhỏ, có thể review và rollback.
- Chạy compiler warnings deprecation/removal.
- Kiểm thử boundary, timezone, locale, security, serialization và performance khi phù hợp.
- Quét lại toàn bộ artifact sau build.
- Điều tra reflection, plugin và dependency động.
- Theo dõi finding còn lại bằng accepted-risk record.
- Cập nhật tài liệu và đóng migration theo tiêu chí đã thống nhất.

## 16. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Deprecated API | API không còn được khuyến nghị sử dụng |
| forRemoval | Thuộc tính báo API được dự định loại bỏ trong tương lai |
| jdeprscan | Công cụ scan bytecode để tìm usage deprecated |
| Target release | Java release mà ứng dụng dự kiến hỗ trợ hoặc triển khai |
| Migration inventory | Danh sách finding, replacement, owner và trạng thái |
| Replacement API | API hoặc thiết kế thay thế usage cũ |
| Semantic difference | Khác biệt về ý nghĩa hoặc hành vi giữa API cũ và mới |
| Direct dependency | Dependency được ứng dụng tham chiếu trực tiếp |
| Transitive dependency | Dependency đến qua một thư viện khác |
| Accepted risk | Finding được giữ lại có chủ đích, kèm lý do và ngày xem xét |
| Regression test | Kiểm thử xác nhận hành vi cũ không bị phá vỡ |
| Compatibility matrix | Ma trận phiên bản JDK, thư viện và nền tảng được hỗ trợ |

Kế hoạch thay thế API cần kết hợp dữ liệu scan, tài liệu chính thức, phân tích ngữ nghĩa và kiểm thử. Hãy dùng jdeprscan để biết usage nào tồn tại, ưu tiên for-removal, chọn replacement theo hợp đồng nghiệp vụ và chỉ đóng migration sau khi đã build, test và scan lại artifact cuối cùng.

## Tài liệu tham khảo

- Oracle JDK 24 — [The jdeprscan Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeprscan.html)
- Oracle — [Java Deprecation](https://docs.oracle.com/en/java/javase/24/core/java-deprecation.html)
- Oracle JDK 24 — [The javac Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)
- OpenJDK — [JDK Migration Guide](https://docs.oracle.com/en/java/javase/24/migrate/)