# Ý nghĩa của SNAPSHOT trong hệ sinh thái kho Maven

Trong Maven, hậu tố **SNAPSHOT** đánh dấu một phiên bản đang được phát triển và có thể tiếp tục thay đổi. Ví dụ, **2.4-SNAPSHOT** là phiên bản phát triển của thư viện 2.4. Nhóm có thể triển khai nhiều lần cùng phiên bản này khi mã nguồn tiếp tục được cập nhật. Maven và kho lưu trữ sử dụng metadata để xác định bản snapshot cụ thể cần tải.

SNAPSHOT giúp các module và dự án khác dùng phiên bản đang phát triển của một thư viện mà không cần tăng số phiên bản sau mỗi lần chỉnh sửa. Tuy nhiên, vì cùng một tọa độ phụ thuộc có thể trỏ tới nội dung khác nhau theo thời điểm, SNAPSHOT ảnh hưởng trực tiếp đến tính ổn định và khả năng tái lập của build. Cần hiểu cách Maven phân giải, lưu cache và cập nhật snapshot để sử dụng đúng trong quá trình phát triển và phát hành.

## 1. Phiên bản SNAPSHOT là gì?

Một phiên bản Maven thông thường có thể là:

    2.4.0

Phiên bản phát triển tương ứng thường được biểu diễn:

    2.4.0-SNAPSHOT

Hậu tố SNAPSHOT phải viết đúng chữ hoa. Nó cho biết phiên bản đó là một bản phát triển chưa được xem như một bản phát hành cố định. Nhà phát triển có thể sửa mã nguồn, triển khai lại và cập nhật nội dung được cung cấp dưới cùng phiên bản SNAPSHOT.

Ví dụ, nhóm đang phát triển thư viện dùng chung có thể duy trì:

    com.example:catalog-api:2.4.0-SNAPSHOT

Một ứng dụng phụ thuộc vào tọa độ này có thể nhận bản mới hơn sau khi nhóm thư viện triển khai snapshot mới và Maven kiểm tra metadata để cập nhật.

Phiên bản phát hành:

    com.example:catalog-api:2.4.0

được dùng để biểu diễn một bản release. Theo quy ước Maven, release nên bất biến sau khi đã phát hành. Kho release của tổ chức nên ngăn ghi đè nội dung đã phát hành để cùng một tọa độ luôn có ý nghĩa ổn định.

SNAPSHOT không có nghĩa là một nhánh Git, một commit cụ thể hoặc một bản build duy nhất. Nó là quy ước phiên bản trong hệ sinh thái Maven.

## 2. Tọa độ phụ thuộc vẫn giữ tên SNAPSHOT

Maven xác định một artifact bằng các tọa độ, thường gồm:

- **groupId:** nhóm hoặc tổ chức sở hữu artifact.
- **artifactId:** tên artifact.
- **version:** phiên bản.
- **packaging:** loại gói, ví dụ jar hoặc pom.
- **classifier:** hậu tố phân biệt biến thể, nếu có.

Ví dụ một dependency:

    <dependency>
        <groupId>com.example</groupId>
        <artifactId>catalog-api</artifactId>
        <version>2.4.0-SNAPSHOT</version>
    </dependency>

Trong POM của ứng dụng, version vẫn được khai báo là **2.4.0-SNAPSHOT**. Khi tải từ một remote repository hỗ trợ snapshot, Maven có thể dùng metadata để tìm một bản timestamped snapshot cụ thể. Người khai báo dependency không cần tự viết timestamp vào POM.

Một snapshot là một phiên bản logic có thể được triển khai nhiều lần. Tọa độ logic giúp các dự án phụ thuộc tiếp tục tham chiếu đến dòng phát triển đó, còn metadata giúp xác định bản triển khai thực tế.

## 3. Vì sao kho Maven dùng timestamped snapshot?

Nếu mỗi lần triển khai đều ghi đè trực tiếp lên cùng một tệp tên catalog-api-2.4.0-SNAPSHOT.jar, người dùng và kho lưu trữ khó phân biệt các lần triển khai khác nhau. Maven hỗ trợ snapshot duy nhất (unique snapshot) bằng cách gắn timestamp và số build vào tên artifact được triển khai.

Ví dụ, tọa độ logic:

    com.example:catalog-api:2.4.0-SNAPSHOT

có thể được lưu trong thư mục phiên bản:

    com/example/catalog-api/2.4.0-SNAPSHOT/

Trong đó, một bản triển khai có thể có tên tệp dạng:

    catalog-api-2.4.0-20261113.061500-3.jar
    catalog-api-2.4.0-20261113.061500-3.pom

Phần timestamp và số build phân biệt lần triển khai cụ thể. Tên thực tế phụ thuộc thời điểm và số thứ tự do quá trình deploy quản lý; ví dụ trên chỉ minh họa định dạng.

Trong POM của ứng dụng, dependency vẫn là **2.4.0-SNAPSHOT**. Maven đọc metadata của phiên bản snapshot để biết bản timestamped nào tương ứng với extension và classifier cần tải.

Một số kho hoặc cấu hình cũ có thể dùng snapshot không duy nhất, tức tệp được lưu với tên chứa trực tiếp hậu tố SNAPSHOT. Không nên giả định mọi repository đều lưu snapshot theo cùng một kiểu tên tệp. Với Maven hiện đại và cấu hình deploy thông dụng, timestamped snapshot là cách triển khai phổ biến.

## 4. Vai trò của maven-metadata.xml

Metadata giúp Maven ánh xạ phiên bản snapshot logic sang bản triển khai cụ thể. Trong thư mục phiên bản snapshot, kho có thể lưu tệp **maven-metadata.xml** chứa timestamp, số build và thông tin các biến thể artifact.

Ví dụ rút gọn về cấu trúc metadata:

    <metadata>
      <version>2.4.0-SNAPSHOT</version>
      <versioning>
        <snapshot>
          <timestamp>20261113.061500</timestamp>
          <buildNumber>3</buildNumber>
        </snapshot>
        <snapshotVersions>
          <snapshotVersion>
            <extension>jar</extension>
            <value>2.4.0-20261113.061500-3</value>
          </snapshotVersion>
          <snapshotVersion>
            <extension>pom</extension>
            <value>2.4.0-20261113.061500-3</value>
          </snapshotVersion>
        </snapshotVersions>
      </versioning>
    </metadata>

Đây là ví dụ giản lược để minh họa các trường quan trọng; metadata thực tế có thể chứa thêm groupId, artifactId, thời điểm cập nhật và classifier.

Khi Maven cần tải **2.4.0-SNAPSHOT**, resolver đọc metadata của repository được chọn, xác định phiên bản snapshot cụ thể phù hợp với loại tệp và classifier, rồi tải artifact tương ứng. Khi có lần deploy mới, metadata có thể được cập nhật để trỏ tới bản timestamped mới hơn.

Metadata là một phần quan trọng của cơ chế snapshot. Nếu metadata ở local cache hoặc trên repository manager bị cũ, Maven có thể tiếp tục dùng bản snapshot trước đó dù một bản mới đã được triển khai.

## 5. Local repository và remote repository

Maven thường làm việc với ít nhất hai loại kho lưu trữ:

### Local repository

Local repository nằm trên máy của người phát triển. Vị trí mặc định thường là:

    ~/.m2/repository

Trên Windows, đường dẫn thường nằm trong thư mục người dùng, ví dụ:

    C:\Users\your-user\.m2\repository

Local repository lưu các artifact đã tải hoặc cài đặt cục bộ, metadata và một số thông tin phục vụ việc phân giải dependency. Khi Maven đã tải một bản snapshot, nó có thể sử dụng bản đã lưu trong local repository cho đến khi chính sách cập nhật yêu cầu kiểm tra lại.

Đường dẫn local repository có thể được thay đổi trong settings.xml bằng thuộc tính localRepository. Vì vậy, không phải dự án nào cũng dùng đúng thư mục mặc định.

### Remote repository

Remote repository là kho trên máy chủ, thường do Maven Central, tổ chức hoặc repository manager nội bộ cung cấp. Dự án có thể tải dependency từ một hoặc nhiều remote repository.

Với SNAPSHOT, remote repository cần cho phép lưu và phân phối snapshot. Một kho chỉ phục vụ release có thể từ chối snapshot hoặc không cung cấp metadata snapshot cần thiết.

Một tổ chức thường tách kho snapshot và kho release để áp dụng chính sách khác nhau:

| Loại kho | Nội dung | Chính sách thường dùng |
| --- | --- | --- |
| Snapshot repository | Phiên bản phát triển như 2.4.0-SNAPSHOT | Cho phép triển khai nhiều lần và cập nhật metadata |
| Release repository | Phiên bản phát hành như 2.4.0 | Hạn chế hoặc cấm ghi đè phiên bản đã phát hành |

Maven có thể dùng repository manager làm điểm truy cập chung, từ đó quản lý proxy, cache, quyền truy cập và chính sách lưu trữ.

## 6. Cấu hình repository để tải snapshot

Trong POM, phần **repositories** khai báo những kho mà Maven có thể sử dụng để phân giải dependency. Ví dụ:

    <repositories>
        <repository>
            <id>company-artifacts</id>
            <url>https://repo.example.com/maven-public/</url>
            <releases>
                <enabled>true</enabled>
            </releases>
            <snapshots>
                <enabled>true</enabled>
                <updatePolicy>interval:30</updatePolicy>
            </snapshots>
        </repository>
    </repositories>

Trong ví dụ:

- **id** là định danh repository, được dùng trong cấu hình và log.
- **url** là địa chỉ repository.
- **releases** bật hoặc tắt việc phân giải release từ kho đó.
- **snapshots** bật hoặc tắt việc phân giải snapshot.
- **updatePolicy** quy định khi nào Maven kiểm tra metadata hoặc artifact cập nhật.

Nếu snapshots bị đặt **enabled=false**, Maven sẽ không dùng repository đó để phân giải snapshot theo cấu hình này. Khi dependency chỉ có ở snapshot repository, build có thể thất bại vì không tìm thấy artifact.

Repository có thể được khai báo trong POM hoặc settings.xml. Settings phù hợp với cấu hình phụ thuộc môi trường, mirror và thông tin truy cập của người dùng. Tránh đặt mật khẩu hoặc token trực tiếp trong POM được commit.

## 7. Cấu hình nơi triển khai snapshot và release

Phần **distributionManagement** trong POM chỉ định nơi Maven triển khai artifact của chính dự án khi chạy lifecycle deploy. Nó khác với **repositories**, vốn dùng để tìm dependency.

Ví dụ:

    <distributionManagement>
        <repository>
            <id>company-releases</id>
            <url>https://repo.example.com/releases/</url>
        </repository>
        <snapshotRepository>
            <id>company-snapshots</id>
            <url>https://repo.example.com/snapshots/</url>
        </snapshotRepository>
    </distributionManagement>

Khi version của dự án kết thúc bằng SNAPSHOT, Maven deploy plugin thường chọn **snapshotRepository**. Với phiên bản release, nó dùng **repository**. Repository manager và plugin deploy thực hiện việc lưu artifact cùng metadata tương ứng.

Thông tin đăng nhập thường được đặt trong settings.xml, với server id khớp id trong distributionManagement:

    <settings>
        <servers>
            <server>
                <id>company-snapshots</id>
                <username>build-user</username>
                <password>token-from-secure-source</password>
            </server>
        </servers>
    </settings>

Đây là ví dụ cấu trúc; thông tin xác thực thực tế cần được cung cấp an toàn qua cấu hình máy hoặc CI secret. Không commit mật khẩu, token hay khóa truy cập vào repository mã nguồn.

Lệnh triển khai thường dùng:

    mvn deploy

Lệnh này chạy các phase trước deploy của Maven lifecycle, tạo artifact và triển khai lên repository được cấu hình. Với version SNAPSHOT, kho snapshot là đích phù hợp.

## 8. Chính sách cập nhật snapshot

Maven không nhất thiết kiểm tra remote repository ở mọi lần chạy. Mỗi repository có thể khai báo **updatePolicy** cho snapshots và releases.

Các giá trị updatePolicy thường dùng:

| Giá trị | Ý nghĩa |
| --- | --- |
| **always** | Kiểm tra cập nhật mỗi lần Maven cần phân giải artifact từ repository đó. |
| **daily** | Kiểm tra tối đa theo chu kỳ hằng ngày; đây là giá trị mặc định phổ biến. |
| **interval:X** | Kiểm tra theo khoảng thời gian X phút. Ví dụ interval:30. |
| **never** | Không tự kiểm tra cập nhật theo chính sách thông thường. |

Ví dụ:

    <snapshots>
        <enabled>true</enabled>
        <updatePolicy>always</updatePolicy>
    </snapshots>

Nếu dùng **daily**, một snapshot mới được deploy lên remote có thể chưa được tải ngay nếu local repository đã kiểm tra trong ngày. Maven có thể tiếp tục dùng bản đã lưu cho đến lần kiểm tra tiếp theo.

Nếu dùng **never**, người dùng có thể tiếp tục dùng bản đã cache lâu dài, trừ khi xóa dữ liệu cục bộ hoặc dùng cơ chế ép cập nhật phù hợp. Cấu hình này không phù hợp nếu nhóm mong muốn mọi build thường xuyên nhận bản snapshot mới nhất.

Update policy có thể cấu hình riêng cho releases và snapshots. Chính sách nên phù hợp với vai trò repository: snapshot thường cần kiểm tra thường xuyên hơn release.

## 9. Ép Maven kiểm tra snapshot mới

Khi cần kiểm tra ngay xem remote đã có snapshot mới hay chưa, có thể chạy:

    mvn -U clean verify

Tùy chọn **-U** yêu cầu Maven kiểm tra các release còn thiếu và snapshot đã cập nhật trên remote repository. Nó hữu ích khi một thành viên vừa deploy snapshot mới nhưng máy khác vẫn đang dùng kết quả cache cũ.

Ví dụ quy trình:

1. Nhóm thư viện triển khai phiên bản **2.4.0-SNAPSHOT** mới.
2. Ứng dụng phụ thuộc vào **2.4.0-SNAPSHOT**.
3. Người phát triển chạy Maven bình thường nhưng local cache chưa đến thời điểm kiểm tra lại.
4. Người phát triển chạy **mvn -U clean verify** để yêu cầu kiểm tra snapshot cập nhật.

Tùy chọn này không sửa dependency version trong POM và không tự triển khai artifact mới. Nó chỉ yêu cầu Maven kiểm tra cập nhật trong quá trình phân giải.

Nếu Maven chạy ở chế độ offline:

    mvn -o verify

Maven không truy cập remote repository. Khi đó, chỉ những artifact đã có sẵn trong local repository mới có thể được sử dụng. Chế độ offline hữu ích khi không có mạng, nhưng không thể lấy snapshot mới vừa được deploy từ xa.

## 10. Vì sao SNAPSHOT làm giảm tính tái lập của build?

Giả sử hai lần build của một ứng dụng đều dùng dependency:

    com.example:catalog-api:2.4.0-SNAPSHOT

Ở lần build thứ nhất, Maven phân giải snapshot timestamped A. Sau đó nhóm thư viện deploy snapshot timestamped B. Một máy khác hoặc lần build sau có thể phân giải B, trong khi máy thứ nhất vẫn dùng A do cache hoặc update policy.

Như vậy, cùng một commit của ứng dụng có thể được build với nội dung dependency khác nhau ở hai thời điểm. Điều này có thể làm kết quả kiểm thử, hành vi ứng dụng hoặc artifact cuối khác nhau.

Các yếu tố thường ảnh hưởng:

- Thời điểm Maven kiểm tra metadata.
- Chính sách updatePolicy.
- Snapshot nào đang được repository manager cung cấp.
- Local repository của máy đã cache phiên bản nào.
- Chế độ offline hoặc mirror đang hoạt động.
- Repository có cho phép ghi đè snapshot hoặc chỉ giữ timestamped snapshot.

Vì vậy, build dựa vào SNAPSHOT có tính linh hoạt cao cho phát triển nhưng không lý tưởng cho bản phát hành cần tái lập. Với phát hành, nên dùng phiên bản release bất biến và lưu lại thông tin dependency, artifact và môi trường build.

## 11. SNAPSHOT có phải là phiên bản mới nhất không?

Không nên nhầm SNAPSHOT với một từ khóa chung có nghĩa “lấy bản mới nhất”.

**2.4.0-SNAPSHOT** là một phiên bản phát triển cụ thể theo quy ước Maven. Maven tìm bản triển khai phù hợp của phiên bản đó thông qua metadata. Nó không có nghĩa lấy bất kỳ version nào mới nhất của artifact.

Ví dụ:

- **2.4.0-SNAPSHOT** yêu cầu dòng phát triển 2.4.0-SNAPSHOT.
- **2.3.1** yêu cầu bản release 2.3.1.
- **2.4.0** yêu cầu bản release 2.4.0.

Mỗi version là một tọa độ khác nhau. Nếu dự án cần nâng từ 2.3.1 lên 2.4.0-SNAPSHOT, phải thay đổi version dependency hoặc quản lý version qua property/BOM tương ứng.

## 12. SNAPSHOT trong dependency bắc cầu

Một dự án có thể không khai báo trực tiếp snapshot nhưng vẫn nhận snapshot qua dependency bắc cầu (transitive dependency).

Ví dụ:

    application
       |
       +----> reporting-client:1.5
                    |
                    +----> catalog-api:2.4.0-SNAPSHOT

Trong trường hợp này, ứng dụng phụ thuộc vào reporting-client release, nhưng POM của reporting-client lại tham chiếu catalog-api snapshot. Kết quả build của ứng dụng vẫn có thể thay đổi khi snapshot bắc cầu được cập nhật.

Có thể xem cây dependency bằng:

    mvn dependency:tree

Hoặc lọc một artifact cụ thể:

    mvn dependency:tree -Dincludes=com.example:catalog-api

Khi điều tra một build thay đổi ngoài dự kiến, cần kiểm tra cả dependency trực tiếp và bắc cầu. Việc chỉ tìm chuỗi SNAPSHOT trong POM gốc có thể bỏ sót một dependency phát sinh từ POM của thư viện khác.

## 13. Quy trình phát triển và phát hành thường dùng

Một quy trình Maven phổ biến sử dụng SNAPSHOT trong giai đoạn phát triển:

1. Nhóm thư viện phát triển trên version như **2.4.0-SNAPSHOT**.
2. Mỗi khi có thay đổi cần chia sẻ, CI hoặc người phát triển triển khai snapshot lên snapshot repository.
3. Các dự án phụ thuộc dùng version SNAPSHOT và cập nhật theo update policy hoặc dùng **-U** khi cần.
4. Khi sẵn sàng phát hành, nhóm chuyển sang version release như **2.4.0**.
5. Artifact release được triển khai lên release repository với chính sách không ghi đè.
6. Sau phát hành, dự án quay lại version phát triển tiếp theo, chẳng hạn **2.4.1-SNAPSHOT**.

Maven Release Plugin có thể hỗ trợ quy trình chuẩn bị phát hành, tạo tag và chuyển version phát triển. Cách cấu hình cụ thể phụ thuộc SCM, plugin và quy ước của tổ chức.

Tách snapshot repository và release repository giúp giảm rủi ro vô tình thay đổi artifact đã phát hành. Nó cũng cho phép áp dụng quyền ghi và chính sách dọn dẹp khác nhau cho từng loại.

## 14. Thực hành tốt khi sử dụng SNAPSHOT

- Dùng SNAPSHOT cho phát triển tích hợp giữa các module khi cần chia sẻ thay đổi thường xuyên.
- Không dùng SNAPSHOT làm dependency không kiểm soát trong artifact phát hành cuối cùng.
- Triển khai snapshot lên repository được thiết kế để lưu phiên bản phát triển.
- Cấu hình updatePolicy phù hợp với nhu cầu nhận bản mới và tải lên repository.
- Dùng **-U** khi cần buộc kiểm tra snapshot mới, thay vì xóa toàn bộ local repository.
- Không giả định máy của mọi thành viên đang dùng cùng một snapshot chỉ vì POM ghi cùng version.
- Ghi lại phiên bản timestamped hoặc checksum/artifact cụ thể khi cần tái hiện một build.
- Tránh cho phép ghi đè release; dùng version mới cho mỗi lần phát hành.
- Kiểm tra dependency bắc cầu để phát hiện snapshot ẩn.
- Giữ thông tin xác thực trong settings.xml hoặc secret store, không commit vào POM.

Nếu cần tái lập build, có thể thay SNAPSHOT bằng release version bất biến, quản lý phiên bản dependency tập trung qua BOM hoặc properties, và lưu lại artifact đã phân giải cùng metadata build. Việc cố định version release vẫn cần đi kèm chính sách repository không ghi đè để bảo đảm tọa độ release thực sự bất biến.

## 15. Chẩn đoán khi Maven không tải snapshot mới

Khi một snapshot vừa được deploy nhưng ứng dụng vẫn dùng bản cũ, hãy kiểm tra theo thứ tự:

1. **Version trong POM:** dependency có đúng hậu tố SNAPSHOT và đúng groupId/artifactId không?
2. **Repository nguồn:** repository được cấu hình có bật snapshots không?
3. **Repository manager:** bản snapshot mới đã được deploy thành công và metadata đã cập nhật chưa?
4. **Update policy:** local repository có đang dùng chính sách daily hoặc never không?
5. **Local cache:** Maven có đang dùng metadata hoặc artifact cũ trong local repository không?
6. **Mirror và settings:** settings.xml có chuyển yêu cầu sang repository khác không?
7. **Offline mode:** lệnh có đang dùng tùy chọn -o hoặc cấu hình offline không?
8. **Dependency bắc cầu:** snapshot có đến từ một thư viện trung gian không?

Một số lệnh hữu ích:

    mvn -U dependency:resolve
    mvn -U clean verify
    mvn dependency:tree
    mvn help:effective-pom

Lệnh đầu tiên yêu cầu kiểm tra và phân giải dependency; lệnh thứ hai thực hiện build cùng kiểm tra cập nhật; dependency:tree cho biết cây dependency; effective-pom giúp xem cấu hình POM sau khi kế thừa và áp dụng profile.

Nếu vẫn nghi ngờ local metadata bị cũ, có thể kiểm tra đúng thư mục artifact trong local repository, thường theo cấu trúc groupId/artifactId/version. Chỉ xóa thư mục phiên bản SNAPSHOT cụ thể khi đã xác định đúng artifact cần tải lại. Không cần xóa toàn bộ ~/.m2/repository, vì thao tác đó buộc Maven tải lại nhiều dependency không liên quan và làm mất cache hữu ích.

## 16. Tổng kết

SNAPSHOT là quy ước Maven cho một phiên bản đang phát triển, có thể được triển khai nhiều lần dưới cùng version logic. Metadata và timestamped snapshots giúp Maven xác định bản triển khai cụ thể trong repository, còn update policy và local cache quyết định thời điểm máy phát triển nhận được bản mới.

SNAPSHOT phù hợp cho tích hợp và thử nghiệm trong quá trình phát triển. Tuy nhiên, vì cùng một tọa độ SNAPSHOT có thể phân giải thành nội dung khác nhau theo thời điểm, nó làm giảm khả năng tái lập của build. Đối với phát hành, nên dùng release version bất biến, tách kho snapshot và release, và ghi lại chính xác artifact được sử dụng.
