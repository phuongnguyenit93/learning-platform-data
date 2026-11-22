# Tách bí mật khỏi cấu hình được lưu trong kho mã

Một dự án Java cần nhiều loại cấu hình để biên dịch, kiểm thử, đóng gói và chạy: địa chỉ repository, tên profile, cổng dịch vụ, tên cơ sở dữ liệu, API key, mật khẩu và thông tin đăng nhập. Một số giá trị có thể chia sẻ công khai trong repository; một số giá trị chỉ được phép dùng bởi một cá nhân, môi trường hoặc hệ thống triển khai.

Nếu commit mật khẩu, token hoặc private key vào Git, thông tin đó có thể bị sao chép tới mọi máy đã clone repository, hệ thống CI, bản sao lưu và lịch sử commit. Xóa giá trị khỏi tệp ở commit sau không làm nó biến mất khỏi lịch sử trước đó. Vì vậy, cần thiết kế cấu hình sao cho mã nguồn và tệp cấu hình dùng chung chỉ chứa thông tin không nhạy cảm, còn bí mật được cung cấp từ môi trường an toàn tại thời điểm build hoặc chạy.

## 1. Phân biệt cấu hình thông thường và bí mật

Cấu hình mô tả cách ứng dụng hoặc công cụ build hoạt động. Không phải mọi giá trị cấu hình đều là bí mật.

| Loại giá trị | Ví dụ | Cách quản lý thường phù hợp |
| --- | --- | --- |
| Cấu hình dùng chung, không nhạy cảm | Tên profile, cổng mặc định, đường dẫn tương đối, tên task | Có thể lưu trong repository |
| Cấu hình môi trường | Host dịch vụ, tên database, URL API | Có thể lưu dưới dạng mẫu hoặc cung cấp theo môi trường |
| Thông tin xác thực | Mật khẩu, API key, access token, client secret | Lưu trong secret manager hoặc kho bí mật của CI |
| Khóa mật mã | Private key, signing key, khóa mã hóa | Lưu trong hệ thống quản lý khóa hoặc secret có kiểm soát truy cập |
| Dữ liệu định danh cá nhân | Tài khoản dịch vụ, thông tin đăng nhập | Chỉ lưu ở nơi được cấp quyền và có chính sách bảo vệ phù hợp |

Một URL repository nội bộ có thể không nhạy cảm, nhưng token dùng để truy cập repository thì có. Tên database có thể được chia sẻ trong cấu hình mẫu, nhưng mật khẩu database không được đưa vào mã nguồn.

Hãy phân loại theo khả năng gây hại nếu giá trị bị lộ. Một chuỗi không có tên password vẫn có thể là bí mật, chẳng hạn chuỗi kết nối có chứa credentials, URL có token trong query string hoặc tệp chứng thư kèm private key.

## 2. Vì sao không lưu bí mật trong repository?

Git được thiết kế để lưu lịch sử thay đổi. Khi một bí mật được commit, nó có thể xuất hiện trong:

- Commit hiện tại và các commit cũ.
- Nhánh khác, tag và pull request.
- Bản clone trên máy của thành viên.
- Cache, log hoặc bản sao lưu của hệ thống CI.
- Fork hoặc bản sao do người khác tạo.

Ngay cả repository private cũng có nhiều bản sao và nhiều người hoặc dịch vụ có quyền truy cập. Quyền private không biến repository thành nơi lưu mật khẩu an toàn.

Ví dụ không nên làm:

    public class DatabaseConfig {
        private static final String USER = "app_user";
        private static final String PASSWORD = "real-password-here";
    }

Không nên đặt bí mật trực tiếp trong:

- Mã Java, tệp properties hoặc YAML.
- build.gradle, build.gradle.kts, pom.xml.
- Script build, script deploy hoặc Dockerfile.
- Tệp test được commit.
- README, ví dụ lệnh hoặc tài liệu hướng dẫn.
- Tệp cấu hình CI có giá trị bí mật viết cứng.

Mã nguồn nên đọc bí mật từ một nguồn được cung cấp bên ngoài. Repository chỉ lưu cách đặt tên biến, cấu trúc cấu hình và hướng dẫn thiết lập.

## 3. Dùng tệp cấu hình mẫu không chứa bí mật

Một cách phổ biến là commit tệp mẫu với các tên thuộc tính cần thiết và giá trị minh họa. Mỗi người hoặc môi trường tạo tệp cấu hình thực tế từ mẫu đó.

Ví dụ, repository có thể chứa:

    .env.example
    application.example.properties

Nội dung .env.example:

    APP_ENV=development
    DB_HOST=localhost
    DB_PORT=5432
    DB_NAME=product_app
    DB_USER=replace-me
    DB_PASSWORD=
    SERVICE_API_KEY=

Tệp mẫu chỉ nêu tên biến và giá trị không nhạy cảm. Không sao chép mật khẩu production vào ví dụ, kể cả khi đã thay đổi một vài ký tự. Giá trị mẫu nên chỉ rõ người dùng phải tự cung cấp thông tin của họ.

Tệp cấu hình local được tạo từ mẫu có thể có tên .env hoặc application-local.properties. Nếu tệp đó chứa bí mật, hãy bỏ qua bằng Git:

    # Local secrets and environment overrides
    .env
    .env.*
    !.env.example
    application-local.properties

Quy tắc này cho phép theo dõi .env.example trong khi bỏ qua các tệp môi trường thực tế theo mẫu đã chọn. Cần điều chỉnh các mẫu theo cấu trúc dự án; tránh dùng quy tắc quá rộng khiến tệp cấu hình dùng chung cũng bị bỏ qua.

### Hướng dẫn thiết lập

README nên hướng dẫn:

1. Sao chép tệp mẫu sang tên tệp local mà ứng dụng đọc.
2. Điền giá trị do quản trị viên hoặc secret manager cấp.
3. Không commit tệp local sau khi điền bí mật.
4. Chọn đúng profile và nguồn cấu hình cho môi trường đang chạy.
5. Thu hồi và cấp lại credentials nếu phát hiện chúng bị lộ.

Tệp mẫu giúp người mới biết ứng dụng cần những giá trị nào mà không phải chia sẻ giá trị thật.

## 4. Đọc bí mật từ biến môi trường trong Java

Biến môi trường là một cách phổ biến để truyền cấu hình nhạy cảm vào tiến trình tại thời điểm chạy. Mã nguồn đọc tên biến, còn giá trị được cung cấp bởi terminal, hệ thống CI hoặc nền tảng triển khai.

Ví dụ:

    public final class DatabaseConfig {
        private DatabaseConfig() {
        }

        public static String requiredEnv(String name) {
            String value = System.getenv(name);
            if (value == null || value.isBlank()) {
                throw new IllegalStateException(
                    "Required environment variable is missing: " + name
                );
            }
            return value;
        }
    }

Một lớp khác có thể lấy thông tin:

    String dbUser = DatabaseConfig.requiredEnv("DB_USER");
    String dbPassword = DatabaseConfig.requiredEnv("DB_PASSWORD");

Tên biến được lưu trong mã nguồn, còn giá trị thực tế không cần xuất hiện trong repository.

### Thiết lập biến môi trường

Trên PowerShell, có thể thiết lập biến trong phiên terminal hiện tại:

    $env:DB_USER = "app_user"
    $env:DB_PASSWORD = "value-provided-locally"
    ./gradlew run

Trên shell kiểu Bash:

    export DB_USER="app_user"
    export DB_PASSWORD="value-provided-locally"
    ./gradlew run

Các ví dụ chỉ minh họa cách truyền giá trị. Không dùng mật khẩu thật trong script được commit, lệnh chia sẻ công khai hoặc ảnh chụp terminal. Biến môi trường thường được truyền xuống tiến trình con và có thể bị lộ qua công cụ chẩn đoán, dump môi trường hoặc log nếu ứng dụng in toàn bộ môi trường. Vì vậy, chỉ cấp những biến cần thiết cho đúng tiến trình và không ghi chúng ra log.

### Kiểm tra cấu hình mà không in giá trị

Khi chẩn đoán thiếu cấu hình, chỉ nên báo tên biến hoặc trạng thái có/không:

    if (System.getenv("SERVICE_API_KEY") == null) {
        System.err.println("SERVICE_API_KEY is not configured");
    }

Không nên viết:

    System.out.println(System.getenv("SERVICE_API_KEY"));

Việc in giá trị ra log có thể khiến bí mật bị lưu trong CI, log tập trung hoặc hệ thống theo dõi lỗi.

## 5. Tách cấu hình chạy ứng dụng khỏi cấu hình build

Ứng dụng cần credentials để kết nối database hoặc dịch vụ bên ngoài. Công cụ build cũng có thể cần credentials để tải dependency từ repository riêng hoặc publish artifact. Hai mục đích này nên được cấu hình riêng.

Ví dụ:

- Ứng dụng đọc DB_PASSWORD khi chạy.
- Gradle hoặc Maven đọc REPOSITORY_TOKEN khi tải hoặc publish artifact.
- CI cung cấp các biến tương ứng cho đúng job cần sử dụng.

Không nên cấp một token có quyền quản trị cho cả ứng dụng, task kiểm thử và task publish nếu từng thành phần chỉ cần quyền hạn nhỏ hơn. Tách credentials theo mục đích giúp giới hạn thiệt hại khi một tiến trình hoặc log bị lộ.

### Gradle: lấy giá trị từ provider

Trong build.gradle.kts, có thể lấy credentials từ biến môi trường:

    repositories {
        maven {
            url = uri("https://packages.example.invalid/maven")
            credentials {
                username = providers.environmentVariable("REPO_USER").orNull
                password = providers.environmentVariable("REPO_PASSWORD").orNull
            }
        }
    }

Đây là ví dụ cấu hình repository; URL dùng tên miền minh họa. Credentials được cung cấp bên ngoài build script. Không viết username hoặc password thật trực tiếp trong tệp build.gradle.kts.

Nếu dự án dùng Gradle property, có thể đọc qua provider:

    val signingKey = providers.gradleProperty("signingKey")

Không lưu giá trị bí mật trong gradle.properties ở gốc repository. Có thể cung cấp Gradle property từ tệp gradle.properties trong thư mục người dùng Gradle hoặc từ nguồn được CI quản lý. Tệp trong thư mục người dùng thường nằm ngoài repository, nhưng vẫn cần bảo vệ quyền truy cập trên máy.

### Maven: đặt credentials trong settings.xml

Maven tách cấu hình dự án trong pom.xml khỏi cấu hình cá nhân hoặc môi trường trong settings.xml. Thông tin xác thực cho server thường được đặt trong phần servers của settings.xml và liên kết với repository bằng cùng giá trị id.

Ví dụ tệp settings.xml cục bộ:

    <settings>
      <servers>
        <server>
          <id>internal-repository</id>
          <username>local-user-placeholder</username>
          <password>local-password-placeholder</password>
        </server>
      </servers>
    </settings>

Đặt tệp người dùng tại vị trí Maven settings của tài khoản, thường là ~/.m2/settings.xml. Không commit tệp chứa credentials này. Trong pom.xml, cấu hình repository dùng id tương ứng nhưng không chứa password.

Maven hỗ trợ cơ chế mã hóa password trong settings. Cơ chế đó có thể giúp tránh để password dạng rõ trong tệp settings, nhưng không nên xem nó như một secret manager hoặc biện pháp bảo vệ tuyệt đối: người có quyền truy cập đủ vào máy và các tệp liên quan có thể có khả năng giải mã. Với CI và môi trường dùng chung, ưu tiên lấy credentials từ kho bí mật được kiểm soát và tạo cấu hình tạm an toàn khi cần.

## 6. Lưu bí mật trong hệ thống CI/CD

CI/CD thường cần credentials để tải dependency private, ký artifact, đẩy image hoặc triển khai. Không nên đưa giá trị đó vào workflow YAML hoặc build script dưới dạng chuỗi cố định.

Quy trình thường dùng:

1. Tạo secret trong phần quản lý secrets của hệ thống CI.
2. Giới hạn quyền đọc secret cho repository, environment, branch hoặc workflow cần dùng.
3. Chỉ truyền secret vào job và bước cần thiết.
4. Không in giá trị, không bật debug có thể tiết lộ nội dung nhạy cảm.
5. Thu hồi hoặc xoay vòng secret theo lịch và khi có sự cố.

Ví dụ workflow có thể tham chiếu một secret đã được cấu hình trong hệ thống CI:

    steps:
      - name: Publish package
        env:
          REPO_USER: ${{ secrets.REPO_USER }}
          REPO_PASSWORD: ${{ secrets.REPO_PASSWORD }}
        run: ./gradlew publish

Đoạn trên là cú pháp minh họa theo GitHub Actions. Tên secret chỉ là tham chiếu; giá trị phải được tạo trong kho secrets của repository hoặc environment. Không lưu giá trị thật vào tệp workflow.

Masking log của CI là lớp bảo vệ bổ sung, không phải lý do để in secret. Giá trị đã biến đổi, mã hóa, chia nhỏ hoặc ghép nối có thể không được bộ lọc nhận diện. Hãy thiết kế script để không xuất secret ngay từ đầu.

### Phạm vi quyền truy cập

Không phải job nào cũng cần tất cả secrets. Ví dụ:

- Job kiểm thử unit có thể không cần credentials production.
- Job tải dependency private chỉ cần quyền đọc.
- Job publish cần quyền ghi vào registry.
- Job deploy chỉ nên có quyền triển khai đúng môi trường được chỉ định.

Tách quyền theo công việc, dùng token ngắn hạn nếu nền tảng hỗ trợ và tránh chia sẻ một token dùng chung cho nhiều pipeline.

## 7. Tránh truyền secret qua command line và log

Một cách có vẻ tiện là truyền password trực tiếp trong đối số:

    ./gradlew publish -PrepoPassword=real-secret

Hoặc:

    mvn deploy -DrepoPassword=real-secret

Không nên làm như vậy. Đối số dòng lệnh có thể xuất hiện trong lịch sử shell, danh sách tiến trình, log CI hoặc thông tin chẩn đoán. Nó cũng có thể bị lưu trong script hoặc tài liệu nếu người dùng sao chép nguyên lệnh.

Ưu tiên biến môi trường được CI hoặc hệ điều hành cung cấp, secret manager, hoặc tệp cấu hình riêng có quyền truy cập hạn chế. Dù dùng nguồn nào, vẫn phải tránh:

- In toàn bộ biến môi trường.
- Bật log HTTP hoặc debug có chứa Authorization header.
- In chuỗi kết nối đầy đủ.
- Đưa secret vào exception message.
- Ghi credentials vào báo cáo kiểm thử.
- Lưu secret trong cache build hoặc artifact được chia sẻ.

Nếu cần chẩn đoán request, hãy ghi endpoint đã loại bỏ thông tin nhạy cảm, mã trạng thái và mã correlation thay vì header hoặc token.

## 8. Dùng .gitignore đúng cách

Tệp .gitignore có thể ngăn những tệp cấu hình local chưa được theo dõi bị thêm vào repository.

Ví dụ:

    # Local environment files
    .env
    .env.*
    !.env.example

    # Local application configuration
    application-local.properties
    application-secret.yml

    # Local build credentials
    gradle.properties

Quy tắc cuối chỉ phù hợp nếu dự án không cần commit một gradle.properties dùng chung. Nếu repository cần tệp này cho cấu hình không nhạy cảm, hãy ignore tệp local theo cách cụ thể hơn hoặc đặt secret ở thư mục người dùng Gradle.

Một số tệp cấu hình có thể vừa chứa cấu hình chung vừa chứa secret. Trong trường hợp đó, tách chúng thành:

- Tệp mẫu hoặc cấu hình mặc định có thể commit.
- Tệp local chứa giá trị riêng, được bỏ qua.
- Secret được cấp từ CI hoặc secret manager khi cần.

### Kiểm tra tệp có bị ignore không

Có thể kiểm tra quy tắc đã khớp:

    git check-ignore -v .env

Xem trạng thái cả tệp bị bỏ qua:

    git status --short --ignored

Lưu ý rằng .gitignore không ngừng theo dõi một tệp đã được commit. Nếu tệp đã nằm trong Git index, thêm quy tắc ignore không loại nó khỏi lịch sử theo dõi.

Để ngừng theo dõi một tệp nhưng giữ bản local:

    git rm --cached application-local.properties

Sau đó kiểm tra git status và commit thay đổi. Tệp sẽ bị loại khỏi phiên bản repository tiếp theo, nhưng vẫn còn trong lịch sử commit cũ. Nếu tệp chứa secret thật, cần xử lý như sự cố lộ secret, không chỉ dựa vào .gitignore.

## 9. Nếu secret đã bị commit hoặc đẩy lên remote

Hãy coi bí mật đã commit là bị lộ, kể cả khi repository private hoặc commit chỉ tồn tại trong thời gian ngắn.

Các bước xử lý nên bắt đầu bằng việc vô hiệu hóa giá trị cũ:

1. Thu hồi token, đổi mật khẩu hoặc xoay vòng khóa bị lộ.
2. Cấp credentials mới với quyền tối thiểu cần thiết.
3. Cập nhật secret manager, CI và môi trường chạy để dùng giá trị mới.
4. Xác định nơi bí mật đã xuất hiện: commit, branch, tag, pull request, log, artifact, cache, fork và bản clone.
5. Xóa giá trị khỏi tệp hiện tại và thêm quy tắc ignore hoặc chuyển sang cấu hình bên ngoài.
6. Nếu chính sách yêu cầu, phối hợp viết lại lịch sử Git để loại bỏ dữ liệu nhạy cảm, sau đó thông báo cho những người có bản clone cần đồng bộ lại.
7. Chạy secret scanning và rà soát lại các nguồn có thể chứa bản sao.

Xóa secret khỏi commit mới không làm nó biến mất khỏi các commit cũ. Viết lại lịch sử có thể giảm khả năng truy cập từ repository chính, nhưng không xóa được các bản sao độc lập đã được người khác lấy về. Vì vậy, thu hồi hoặc xoay vòng credentials là bước ưu tiên; làm sạch lịch sử là bước xử lý bổ sung.

Không nên tiếp tục sử dụng token cũ trong lúc chờ dọn lịch sử. Nếu secret có quyền truy cập rộng, cần đánh giá hoạt động bất thường trong khoảng thời gian nó có thể bị lộ.

## 10. Mã hóa tệp cấu hình có giải quyết được vấn đề không?

Mã hóa có thể hữu ích khi cần lưu trữ hoặc chia sẻ một số cấu hình nhạy cảm, nhưng cần xác định ai giữ khóa giải mã và ở đâu.

Nếu repository chứa tệp đã mã hóa nhưng khóa giải mã được commit cùng repository, người lấy được repository có cả hai thành phần và có thể giải mã. Khi đó, mã hóa không cung cấp ranh giới bảo mật hữu ích.

Một thiết kế phù hợp hơn là:

- Lưu tệp cấu hình mã hóa trong nơi được phép chia sẻ nếu có nhu cầu.
- Giữ khóa giải mã trong secret manager hoặc hệ thống quản lý khóa độc lập.
- Chỉ cấp quyền giải mã cho người hoặc job thực sự cần.
- Ghi nhận cách xoay vòng khóa và xử lý khi thành viên rời nhóm.

Đối với nhiều dự án, không cần commit tệp secret mã hóa. Sử dụng secret manager của nền tảng CI hoặc môi trường triển khai thường đơn giản và dễ kiểm soát hơn.

## 11. Quy tắc bảo vệ bí mật trong build và runtime

### Không để secret xuất hiện trong đầu ra build

Task build có thể tạo JAR, báo cáo, manifest, metadata hoặc file cấu hình được đóng gói. Hãy kiểm tra để chắc chắn credentials không bị chép vào artifact. Không đặt password trong resource mặc định hoặc thuộc tính build được ghi lại trong manifest.

Nếu task cần secret để ký artifact, chỉ dùng nó trong bước ký và không ghi giá trị vào đầu ra. Kiểm tra log để bảo đảm lệnh ký không in khóa hoặc password.

### Không dùng secret production trong unit test

Unit test nên dùng dữ liệu giả và dependency thay thế. Integration test có thể cần dịch vụ thật trong môi trường kiểm thử, nhưng credentials nên được cấp riêng cho môi trường đó với quyền và dữ liệu giới hạn. Không dùng tài khoản production chỉ để chạy test.

### Giữ cấu hình an toàn theo môi trường

Local, CI, staging và production thường có host, database và credentials khác nhau. Tên biến có thể nhất quán, nhưng giá trị được cấp từ từng môi trường.

Ví dụ:

    DB_HOST
    DB_NAME
    DB_USER
    DB_PASSWORD

Ứng dụng đọc cùng một bộ tên biến, còn nền tảng triển khai cung cấp giá trị phù hợp cho môi trường đang chạy. Cách này giúp tránh thay đổi mã nguồn chỉ vì chuyển từ local sang staging hoặc production.

### Giới hạn quyền và thời hạn

Mỗi secret nên có:

- Chủ sở hữu hoặc nhóm chịu trách nhiệm.
- Mục đích sử dụng rõ ràng.
- Phạm vi quyền tối thiểu.
- Thời hạn hoặc lịch xoay vòng.
- Quy trình thu hồi khi bị lộ hoặc không còn cần thiết.

Token đọc package không nên có quyền xóa repository. Credentials dùng cho kiểm thử không nên có quyền ghi dữ liệu production. Giới hạn quyền làm giảm tác động khi secret bị lộ.

## 12. Ví dụ cấu trúc repository an toàn

Một dự án Java có thể tổ chức như sau:

    product-app/
      .gitignore
      README.md
      pom.xml
      src/
        main/
          java/
          resources/
            application.properties
        test/
          java/
          resources/
      config/
        application.example.properties
      local/
        application-local.properties

Trong ví dụ này:

- README.md hướng dẫn cách thiết lập và chạy ứng dụng.
- application.example.properties chứa tên thuộc tính và giá trị minh họa, không chứa secret.
- application-local.properties chứa giá trị riêng của máy và được .gitignore bỏ qua.
- application.properties chứa cấu hình mặc định không nhạy cảm hoặc tham chiếu đến biến môi trường.
- CI cấp secret vào đúng bước cần thiết.

Nếu không cần thư mục local trong repository, người dùng có thể tạo tệp local bên ngoài cây mã nguồn. Điều quan trọng là ứng dụng có quy tắc rõ ràng để nạp cấu hình và không vô tình đóng gói tệp local vào artifact.

## 13. Kiểm tra secret trước khi commit

Trước khi commit, cần xem nội dung thay đổi thay vì chỉ dựa vào trạng thái tên tệp:

    git status --short
    git diff --cached

Kiểm tra các tệp được stage, đặc biệt là:

- Tệp properties, YAML, JSON và XML.
- Script shell, PowerShell và build script.
- Workflow CI.
- Tệp cấu hình IDE.
- Tài liệu và ví dụ lệnh.
- Tệp chứng thư, khóa và cấu hình deploy.

Có thể tích hợp secret scanning vào pre-commit, CI hoặc nền tảng quản lý repository. Scanner giúp phát hiện chuỗi có hình dạng giống token, private key hoặc credential đã biết. Nó không thay thế việc thiết kế nguồn cấu hình đúng và không bảo đảm phát hiện mọi bí mật.

Nếu scanner phát hiện giá trị nghi ngờ, xác minh xem đó có phải secret thật hay không bằng quy trình an toàn. Không sao chép giá trị nghi ngờ vào issue hoặc chat công khai để hỏi.

## 14. Quy trình thiết lập cho thành viên mới

Một thành viên mới nên có thể clone repository và thiết lập môi trường mà không cần nhận một tệp cấu hình chứa mọi mật khẩu từ người khác.

Quy trình đề xuất:

1. Clone repository và đọc README.
2. Xác định các biến môi trường hoặc thuộc tính cấu hình được liệt kê trong tệp mẫu.
3. Xin quyền truy cập qua quy trình quản lý danh tính của nhóm.
4. Tạo cấu hình local hoặc đăng nhập vào secret manager theo hướng dẫn.
5. Cấp giá trị chỉ cho tiến trình hoặc môi trường cần dùng.
6. Chạy build và kiểm thử với credentials có quyền tối thiểu.
7. Kiểm tra git status để chắc chắn tệp local và secret không bị stage.

Không gửi mật khẩu qua commit, chat nhóm hoặc tài liệu chia sẻ rộng. Dùng kênh cấp quyền và chia sẻ bí mật đã được tổ chức phê duyệt.

## 15. Những sai lầm thường gặp

### Đổi tên secret thành một thuộc tính cấu hình nhưng vẫn commit giá trị

Chuyển password từ mã Java sang application.properties không giải quyết vấn đề nếu tệp properties vẫn được commit với password thật. Cần tách giá trị ra khỏi tệp được quản lý.

### Chỉ xóa secret khỏi phiên bản mới nhất

Commit xóa một dòng không làm mất các phiên bản cũ. Hãy thu hồi secret và xử lý lịch sử, log, artifact hoặc bản sao theo quy trình sự cố.

### Nghĩ rằng repository private là nơi lưu bí mật

Repository private vẫn có nhiều người, dịch vụ và bản clone truy cập. Hãy dùng hệ thống quản lý secret chuyên dụng.

### In secret để kiểm tra cấu hình

Không cần in password để xác nhận nó đã được nạp. Chỉ ghi trạng thái có hoặc thiếu, và che dữ liệu nhạy cảm trong log.

### Dùng một token quyền cao cho mọi môi trường

Token dùng chung cho local, CI và production làm tăng phạm vi thiệt hại. Hãy tách theo môi trường và mục đích, giới hạn quyền và thời hạn.

### Coi .gitignore là biện pháp xóa dữ liệu đã commit

.gitignore chỉ giúp bỏ qua tệp chưa được theo dõi. Tệp đã commit vẫn nằm trong lịch sử cho tới khi được xử lý riêng; secret đã lộ cần được thu hồi.

## 16. Nguyên tắc tổ chức cấu hình an toàn

Một cấu hình dễ bảo trì và an toàn thường tuân theo các nguyên tắc:

- Commit cấu trúc cấu hình, tên biến, giá trị mặc định không nhạy cảm và tệp mẫu.
- Cấp secret từ secret manager, biến môi trường hoặc tệp local có quyền truy cập hạn chế.
- Tách cấu hình build khỏi cấu hình runtime và tách credentials theo mục đích.
- Không đưa secret vào mã nguồn, build script, đối số dòng lệnh, log hoặc artifact.
- Giới hạn quyền, phạm vi và thời hạn của từng credential.
- Dùng secret scanning và xem lại diff trước khi commit.
- Xoay vòng ngay khi có dấu hiệu lộ; làm sạch lịch sử là biện pháp bổ sung.

Mục tiêu là để repository có đủ thông tin giúp mọi người hiểu và tái tạo quy trình build, trong khi chỉ những người hoặc tiến trình được cấp quyền mới có thể lấy giá trị bí mật. Khi cấu hình được tách đúng, cùng một mã nguồn có thể chạy ở local, CI, staging và production bằng những credentials riêng mà không phải sửa hoặc commit lại mã nguồn.
