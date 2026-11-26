Bạn giải thích pipeline biên dịch Java chuyển mã nguồn .java thành bytecode .class qua những giai đoạn chính nào?
Bạn phân biệt nhiệm vụ của javac với Java Virtual Machine khi chạy một chương trình Java như thế nào?
Bạn sẽ mô tả mối quan hệ giữa Java Language Specification và Java Virtual Machine Specification trong xử lý chương trình như thế nào?
Bạn phân biệt lexical analysis với syntax parsing trong quá trình javac đọc một source file ra sao?
Bạn sẽ chỉ ra vì sao một chuỗi ký tự không hợp lệ có thể gây lỗi lexical trước khi compiler kiểm tra kiểu như thế nào?
Bạn mô tả abstract syntax tree (AST) biểu diễn cấu trúc lệnh, biểu thức và khai báo như thế nào?
Bạn phân biệt lỗi cú pháp thiếu dấu ngoặc với lỗi ngữ nghĩa tham chiếu biến chưa khai báo như thế nào?
Bạn sẽ dùng thông tin vị trí dòng và cột từ compiler diagnostic để xác định token gây lỗi ra sao?
Bạn giải thích symbol table có vai trò gì trong quá trình compiler nhận diện tên biến, phương thức và kiểu?
Bạn sẽ mô tả name resolution xử lý một tên trùng giữa local variable, field và imported type như thế nào?
Bạn phân biệt lỗi cannot find symbol với lỗi incompatible types theo giai đoạn kiểm tra nào?
Bạn sẽ xác định cách javac tra cứu các declarations khi gặp một class có package và import statements ra sao?
Bạn mô tả type attribution kiểm tra biểu thức và gán kiểu theo ngữ cảnh được mong đợi như thế nào?
Bạn phân biệt compile-time type checking với runtime checks như ClassCastException ra sao?
Bạn sẽ giải thích vì sao Java type erasure cho phép generic source type nhưng .class không chứa đầy đủ tham số kiểu lúc chạy như thế nào?
Bạn phân biệt compile-time constant expressions với giá trị chỉ tính được ở runtime theo tác động sinh bytecode như thế nào?
Bạn sẽ xác định điều kiện nào khiến Java compiler báo unreachable statement hoặc definite assignment error như thế nào?
Bạn mô tả definite assignment analysis bảo đảm local variable được gán trước khi đọc như thế nào?
Bạn sẽ phân biệt checked exception analysis của javac với exception được ném thực tế lúc chạy ra sao?
Bạn phân tích vì sao một method có thể compile dù vẫn phát sinh NullPointerException khi thực thi như thế nào?
Bạn sẽ xác định lúc nào compiler có thể áp dụng constant folding mà không làm thay đổi semantics của chương trình ra sao?
Bạn mô tả annotation processing được thực hiện ở đâu so với các bước phân tích và sinh class files như thế nào?
Bạn phân biệt source code generation từ annotation processor với bytecode generation của javac như thế nào?
Bạn sẽ xác định cách compiler nhận source files mới do processor tạo ra trong các processing rounds tiếp theo ra sao?
Bạn giải thích class-file emission là bước tạo các cấu trúc như constant pool, methods và attributes như thế nào?
Bạn sẽ phân biệt class loading, linking và initialization của JVM với các giai đoạn biên dịch trước đó ra sao?
Bạn mô tả vì sao Java bytecode mang tính nền tảng độc lập nhưng vẫn gắn class file version và API availability ra sao?
Bạn sẽ xác định khi nào compiler cần đọc .class của dependencies thay vì nguồn .java có sẵn như thế nào?
Bạn phân tích nguy cơ lệch kết quả giữa IDE compiler và javac dùng trong CI khi hai bên không cùng cấu hình như thế nào?
Bạn sẽ tổ chức một bước chẩn đoán theo thứ tự lexical, parsing, name/type resolution và output để tìm nguyên nhân build fail ra sao?
Bạn giải thích method overload resolution được javac quyết định từ kiểu tại thời điểm biên dịch như thế nào?
Bạn phân biệt overload selection với dynamic method dispatch của override tại runtime ra sao?
Bạn sẽ mô tả autoboxing và unboxing tham gia việc tìm phương thức overload phù hợp theo quy tắc nào?
Bạn phân tích nguy cơ khai báo overload nhận long và Integer khiến lời gọi với literal gây kết quả bất ngờ như thế nào?
Bạn sẽ xác định khi nào varargs được xét so với fixed-arity methods trong overload resolution ra sao?
Bạn phân biệt overload ambiguity với lỗi method không accessible từ package khác như thế nào?
Bạn sẽ giải thích generic method type inference chịu ảnh hưởng bởi target type trong phép gán hoặc return như thế nào?
Bạn mô tả diamond operator dùng ngữ cảnh để suy luận các type arguments theo cách nào?
Bạn sẽ xác định vì sao một lambda expression chỉ được chấp nhận khi có target functional interface phù hợp ra sao?
Bạn phân biệt method reference overload resolution với lambda expression về thông tin kiểu cần suy luận như thế nào?
Bạn phân tích trường hợp hai overloaded functional interfaces khiến lambda invocation trở nên ambiguous ra sao?
Bạn sẽ giải thích erasure của List<String> và List<Integer> ảnh hưởng việc khai báo hai overloaded methods ra sao?
Bạn mô tả compiler sinh bridge method cho generic overriding hoặc covariant return theo mục đích tương thích nào?
Bạn sẽ dùng javap để nhận ra ACC_BRIDGE và ACC_SYNTHETIC của method được compiler tạo ra như thế nào?
Bạn phân biệt raw types warning với unchecked cast warning và khả năng xuất hiện lỗi runtime ra sao?
Bạn sẽ xác định cách javac kiểm tra bounded type parameter và wildcard khi gán generic collections như thế nào?
Bạn giải thích capture conversion cho wildcard generic type ảnh hưởng những lời gọi method nào?
Bạn sẽ phân biệt wildcard với upper bound extends và lower bound super từ góc nhìn compile-time assignability ra sao?
Bạn phân tích vì sao generics invariance khiến List<Subclass> không phải List<Superclass> như thế nào?
Bạn sẽ mô tả cách compiler xử lý pattern matching for instanceof để xác định phạm vi tồn tại của biến mẫu như thế nào?
Bạn phân biệt source-level feature với class-file feature khi compiler hạ cú pháp mới xuống bytecode ra sao?
Bạn sẽ xác định cách javac báo lỗi khi dùng record hoặc sealed class dưới một --release không hỗ trợ như thế nào?
Bạn giải thích record components được ánh xạ thành fields, accessor methods và metadata class file ra sao?
Bạn sẽ dùng javap để phân tích cấu trúc bytecode do một lambda hoặc method reference tạo ra như thế nào?
Bạn phân biệt invokedynamic của lambda với lời gọi invokeinterface thông thường qua thông tin class file như thế nào?
Bạn sẽ xác định các trường hợp compiler phát sinh synthetic methods hoặc fields khi hỗ trợ những cấu trúc ngôn ngữ nào?
Bạn phân tích ảnh hưởng của null literals đến overload resolution và các lỗi ambiguous method call ra sao?
Bạn sẽ thiết kế bài kiểm thử compile-time cho một API generic để phát hiện lỗi breaking change trước khi chạy unit tests như thế nào?
Bạn giải thích classpath quyết định các class và packages mà javac có thể truy cập trong quá trình biên dịch như thế nào?
Bạn phân biệt application classpath với boot classpath lịch sử và system modules của JDK hiện đại ra sao?
Bạn sẽ sử dụng -classpath hoặc -cp để chỉ định dependencies trong lệnh javac như thế nào?
Bạn phân tích vì sao dấu phân tách phần tử classpath khác nhau trên Windows và Linux ra sao?
Bạn sẽ xác định thứ tự các entries trong classpath ảnh hưởng chọn duplicate classes theo cơ chế nào?
Bạn phân biệt compile-time dependency với runtime-only dependency khi thư viện được dùng qua reflection như thế nào?
Bạn sẽ giải thích vì sao compiler tìm thấy interface nhưng không tìm được một return type từ dependency chuyển tiếp ra sao?
Bạn mô tả package visibility và public type visibility ảnh hưởng quyền sử dụng class trên classpath như thế nào?
Bạn sẽ xác định tại sao import một package không tồn tại gây lỗi dù JAR tương ứng có trong build cache ra sao?
Bạn phân tích rủi ro dùng wildcard classpath khiến dependency order và phiên bản JAR khó dự đoán như thế nào?
Bạn sẽ tổ chức dependency graph để tránh xung đột hai thư viện cùng cung cấp class có tên đầy đủ giống nhau ra sao?
Bạn phân biệt classpath với module path khi javac làm việc với Java Platform Module System như thế nào?
Bạn sẽ dùng --module-path để cung cấp named modules và --class-path cho classpath libraries theo tình huống nào?
Bạn giải thích module-info.java khai báo requires và exports ảnh hưởng quyền truy cập compile-time như thế nào?
Bạn phân biệt requires với requires transitive trong khả năng module consumer đọc dependencies ra sao?
Bạn sẽ xác định cách exports của một module khác với opens dùng cho reflection tại runtime như thế nào?
Bạn phân tích vì sao một package có class public vẫn không thể được import từ module khác nếu không được exports ra sao?
Bạn sẽ kiểm tra lỗi module not found và package is not visible khi chuyển dự án từ classpath sang module path như thế nào?
Bạn mô tả automatic module name được suy ra hoặc khai báo trong JAR ảnh hưởng dependency resolution ra sao?
Bạn sẽ đánh giá rủi ro tên automatic module thay đổi khi đổi tên file JAR như thế nào?
Bạn phân biệt unnamed module với named module về cách đọc các module khác trong compile-time configuration ra sao?
Bạn sẽ dùng --module-source-path khi biên dịch nhiều source modules cùng lúc theo cách nào?
Bạn sẽ tổ chức -d cho output class directories để tránh đặt files đầu ra chung với source như thế nào?
Bạn phân tích lý do split packages không phù hợp với named module configurations và cách xử lý ra sao?
Bạn sẽ xác định khi nào dùng --add-exports như một giải pháp tạm thời và những rủi ro khi phụ thuộc internal JDK APIs ra sao?
Bạn phân biệt --add-reads và --add-modules theo tác dụng điều chỉnh module graph lúc biên dịch ra sao?
Bạn sẽ kiểm tra một API thuộc java.base hay một JDK module khác khi compile cần requires như thế nào?
Bạn mô tả cách --limit-modules hạn chế tập observable modules cho một lần biên dịch theo mục đích nào?
Bạn phân tích vì sao cùng nguồn Java có thể compile trong classpath mode nhưng lỗi khi chuyển sang module-path mode ra sao?
Bạn sẽ dùng jdeps để xác định phụ thuộc giữa packages hoặc modules trước khi thiết kế module descriptor như thế nào?
Bạn sẽ lập kế hoạch migration từng bước từ classpath-based application sang JPMS mà vẫn giữ build reproducible như thế nào?
Bạn giải thích sự khác biệt giữa -source, -target và --release trong công cụ javac như thế nào?
Bạn sẽ dùng --release để bảo đảm source code không gọi API của JDK mới hơn runtime mục tiêu ra sao?
Bạn phân tích vì sao chỉ dùng -target vẫn có thể biên dịch nhầm lời gọi API không tồn tại ở runtime cũ như thế nào?
Bạn sẽ xác định class file major version từ output .class và liên hệ nó với JDK target như thế nào?
Bạn phân biệt UnsupportedClassVersionError tại runtime với lỗi cú pháp tại compile time ra sao?
Bạn sẽ kiểm tra javac -version và java -version khi một dự án compile thành công nhưng không chạy được ra sao?
Bạn mô tả JDK toolchain đảm bảo Gradle hoặc Maven dùng compiler khác với JDK chạy build tool như thế nào?
Bạn sẽ cấu hình Maven Compiler Plugin để chọn --release cho dự án theo yêu cầu tương thích nào?
Bạn phân biệt Gradle Java toolchains với cài đặt JAVA_HOME toàn cục theo khả năng kiểm soát phiên bản ra sao?
Bạn sẽ tổ chức CI matrix build cho các bản JDK được hỗ trợ mà không bỏ sót vấn đề tương thích ra sao?
Bạn phân tích vì sao thư viện phụ thuộc được biên dịch bằng JDK mới có thể làm javac trên JDK cũ báo lỗi class version ra sao?
Bạn sẽ dùng --enable-preview khi thử preview language features và nhận diện nghĩa vụ tại runtime như thế nào?
Bạn phân biệt preview feature với incubator module về yêu cầu flags và phạm vi hỗ trợ ra sao?
Bạn sẽ xác định rủi ro phát hành bytecode dựa trên preview feature cho người dùng production ra sao?
Bạn mô tả khác biệt giữa source compatibility, binary compatibility và behavioral compatibility khi nâng Java library như thế nào?
Bạn phân biệt thay đổi public method signature với thay đổi implementation body theo nguy cơ phá binary compatibility ra sao?
Bạn sẽ giải thích vì sao NoSuchMethodError có thể xuất hiện tại runtime dù một artifact đã compile thành công như thế nào?
Bạn phân tích vì sao NoClassDefFoundError có thể xuất hiện sau khi compile khi dependency bị thiếu ở runtime ra sao?
Bạn sẽ thiết kế bài kiểm tra linkage với các phiên bản library được hỗ trợ để phát hiện lỗi trước deploy như thế nào?
Bạn phân biệt multi-release JAR với một JAR chứa duy nhất class implementation theo runtime JDK nào?
Bạn sẽ xác định cách META-INF/versions được JVM và tooling nhìn nhận trong multi-release JAR ra sao?
Bạn sẽ kiểm tra API của các biến thể class trong multi-release JAR không vô tình khác nhau ngoài chủ đích ra sao?
Bạn phân tích vì sao Java version được IDE dùng và toolchain được CLI build dùng phải được đối chiếu độc lập ra sao?
Bạn sẽ xác định encoding nguồn qua -encoding UTF-8 để compilation không phụ thuộc default charset theo hệ điều hành ra sao?
Bạn phân biệt source file encoding với encoding của messages và output generated files như thế nào?
Bạn sẽ đặt -parameters khi cần giữ tên tham số method cho reflection libraries theo yêu cầu nào?
Bạn phân tích vì sao tắt debug attributes bằng -g:none không tương đương loại bỏ mọi tên identifier khỏi class file ra sao?
Bạn sẽ xác định khi nào cần giữ compatibility với JDK bản vá nhỏ khác nhau trong build và runtime test như thế nào?
Bạn sẽ thiết kế build reproducibility bảo đảm cùng source, compiler options và dependencies tạo đầu ra có thể kiểm tra ra sao?
Bạn giải thích Java annotation processing theo JSR 269 hoạt động trong quá trình javac như thế nào?
Bạn phân biệt annotation được xử lý ở compile time với annotation được giữ tới runtime thông qua @Retention ra sao?
Bạn sẽ khai báo một annotation processor bằng AbstractProcessor theo vòng đời nào?
Bạn mô tả @SupportedAnnotationTypes và @SupportedSourceVersion giúp processor công bố khả năng hỗ trợ như thế nào?
Bạn sẽ sử dụng ProcessingEnvironment để truy cập Filer, Messager, Elements và Types như thế nào?
Bạn phân biệt Element với TypeMirror khi duyệt cấu trúc chương trình trong annotation processor ra sao?
Bạn sẽ dùng RoundEnvironment lấy những phần tử mang annotation cụ thể trong một processing round như thế nào?
Bạn giải thích vì sao annotation processing có nhiều rounds khi processor sinh Java source mới như thế nào?
Bạn sẽ xác định processingOver() và errorRaised() ảnh hưởng bước xử lý cuối của processor ra sao?
Bạn phân biệt return true và false từ Processor.process về việc annotation được claim với processors khác như thế nào?
Bạn sẽ tạo Java source bằng Filer.createSourceFile mà không tự ý ghi file vào source directory ra sao?
Bạn phân tích rủi ro processor tạo cùng tên generated file ở nhiều rounds gây FilerException như thế nào?
Bạn sẽ dùng Messager.printMessage để báo lỗi annotation kèm Element nhằm xác định đúng dòng source ra sao?
Bạn phân biệt Diagnostic.Kind.ERROR với WARNING và MANDATORY_WARNING theo ảnh hưởng tới build ra sao?
Bạn sẽ kiểm tra annotation processor phát hiện method signature không hợp lệ rồi đưa ra diagnostic rõ ràng như thế nào?
Bạn mô tả cách auto-discovery processors qua META-INF/services/javax.annotation.processing.Processor hoạt động như thế nào?
Bạn sẽ sử dụng -processor để chọn chính xác annotation processor khi build cần kiểm soát thành phần thực thi ra sao?
Bạn phân biệt -processorpath với --processor-module-path theo cách cung cấp processors từ classpath hay named modules ra sao?
Bạn sẽ quyết định khi nào dùng -proc:only để chạy annotation processing mà không phát sinh class files như thế nào?
Bạn sẽ xác định tác dụng của -proc:none khi cần tắt toàn bộ annotation processing để khoanh vùng build failure ra sao?
Bạn phân tích rủi ro dựa vào auto-discovery khi nâng JDK khiến processor không được kích hoạt như trước ra sao?
Bạn sẽ dùng -XprintRounds và -XprintProcessorInfo để chẩn đoán các vòng xử lý và processors tham gia như thế nào?
Bạn phân biệt annotation processor với compiler plugin dùng internal javac APIs về tính ổn định giao diện ra sao?
Bạn sẽ thiết kế processor tạo mã deterministic để incremental builds và CI cho kết quả nhất quán như thế nào?
Bạn phân tích vì sao annotation processor đọc clock hoặc filesystem không khai báo có thể làm build không tái lập ra sao?
Bạn sẽ phân biệt isolating processor và aggregating processor theo ảnh hưởng tới incremental compilation của build tool ra sao?
Bạn sẽ cấu hình generated sources directory bằng -s để kiểm tra và dọn output đúng vị trí như thế nào?
Bạn phân tích rủi ro generated classes cũ tồn tại sau khi xóa annotation khiến build vẫn thành công giả ra sao?
Bạn sẽ kiểm thử annotation processor bằng các input sources sai và đúng để so sánh diagnostics và generated files như thế nào?
Bạn sẽ đánh giá khác biệt giữa Lombok dùng compiler integration và annotation processor thuần JSR 269 trong tương thích compiler ra sao?
Bạn phân tích nguy cơ annotation processor là code được thực thi trong máy build khi xử lý dependency chưa được kiểm toán ra sao?
Bạn giải thích javax.tools.JavaCompiler cho phép ứng dụng Java gọi compiler theo lập trình như thế nào?
Bạn sẽ lấy compiler qua ToolProvider.getSystemJavaCompiler và xử lý môi trường chỉ có runtime không cung cấp compiler ra sao?
Bạn phân biệt JavaCompiler API với chạy subprocess javac qua ProcessBuilder theo kiểm soát dữ liệu và diagnostics như thế nào?
Bạn sẽ dùng JavaCompiler.CompilationTask để thực thi compilation với options và compilation units như thế nào?
Bạn mô tả StandardJavaFileManager giúp quản lý source files, classpath và output locations ra sao?
Bạn sẽ xác định vì sao cần đóng StandardJavaFileManager sau mỗi session compile theo lifecycle nào?
Bạn phân biệt JavaFileObject với FileObject khi compiler thao tác source, class và tài nguyên ra sao?
Bạn sẽ tạo SimpleJavaFileObject biểu diễn source code nằm trong String thay vì file trên đĩa như thế nào?
Bạn sẽ lựa chọn URI scheme và JavaFileObject.Kind.SOURCE phù hợp khi cung cấp source trong bộ nhớ như thế nào?
Bạn mô tả getCharContent của SimpleJavaFileObject cung cấp nội dung source cho compiler như thế nào?
Bạn sẽ tạo DiagnosticCollector<JavaFileObject> để thu lỗi, cảnh báo, vị trí source và mã diagnostic như thế nào?
Bạn phân biệt DiagnosticListener với DiagnosticCollector theo cách tiêu thụ compiler messages như thế nào?
Bạn sẽ kiểm tra compilationTask.call() trả false so với ném exception bất thường trong quy trình xử lý ra sao?
Bạn sẽ cấu hình -classpath, --module-path, -d và --release trong options truyền cho JavaCompiler như thế nào?
Bạn phân tích rủi ro truyền user-supplied compiler flags tùy ý khi ứng dụng cho phép biên dịch source bên ngoài ra sao?
Bạn sẽ thiết kế ForwardingJavaFileManager để nhận .class bytes thay vì ghi class files ra filesystem như thế nào?
Bạn mô tả getJavaFileForOutput của custom JavaFileManager được dùng để chuyển bytecode tới in-memory JavaFileObject ra sao?
Bạn sẽ xây dựng JavaFileObject.Kind.CLASS có openOutputStream ghi bytecode vào ByteArrayOutputStream như thế nào?
Bạn phân biệt biên dịch trong bộ nhớ với nạp và chạy bytecode trong cùng JVM theo những ranh giới bảo mật nào?
Bạn sẽ sử dụng ClassLoader.defineClass thông qua custom ClassLoader để nạp class bytes đã sinh theo điều kiện nào?
Bạn phân tích rủi ro class name collision khi nhiều lần biên dịch cùng binary name trong một ClassLoader ra sao?
Bạn sẽ cô lập các class definitions qua ClassLoader instances thay vì kỳ vọng unload một class độc lập như thế nào?
Bạn sẽ xác định thời điểm ClassLoader có thể được GC thu hồi khi code đã nạp giữ static references hoặc threads như thế nào?
Bạn phân biệt compile errors với LinkageError hoặc ClassNotFoundException phát sinh sau khi custom class loader nạp mã như thế nào?
Bạn sẽ tổ chức in-memory compilation nhiều source files có dependencies lẫn nhau theo cách nào?
Bạn sẽ xác định khi nào compiler cần truy cập classpath classes thay vì nguồn in-memory được cung cấp như thế nào?
Bạn phân tích rủi ro JavaFileManager chia sẻ mutable output state giữa các compilation tasks chạy đồng thời ra sao?
Bạn sẽ thiết kế timeout và resource limits khi cung cấp dịch vụ compile code do người dùng nhập như thế nào?
Bạn phân tích vì sao chỉ hạn chế compiler options không tạo sandbox an toàn nếu annotation processors có thể chạy tùy ý ra sao?
Bạn sẽ quyết định khi nào phải biên dịch code không tin cậy trong isolated process/container thay vì JVM sản xuất ra sao?
Bạn sẽ trả diagnostics có vị trí source cho IDE-like UI nhưng tránh lộ file paths hoặc dữ liệu bí mật của máy chủ như thế nào?
Bạn sẽ viết test end-to-end in-memory compile, load và invoke trong môi trường được cô lập để xác minh kết quả như thế nào?
Bạn giải thích định dạng class file chứa magic number, version, constant pool và các bảng cấu trúc như thế nào?
Bạn sẽ dùng javap -c để xem instruction bytecode của một phương thức sau biên dịch như thế nào?
Bạn phân biệt javap -v với javap -p khi cần metadata chi tiết và private members như thế nào?
Bạn sẽ xác định major version của file .class qua javap -verbose để chẩn đoán phiên bản Java ra sao?
Bạn mô tả constant pool giữ những loại tham chiếu symbolic nào cần cho linking lúc chạy như thế nào?
Bạn phân biệt CONSTANT_Class và CONSTANT_Methodref theo vai trò trong một class file ra sao?
Bạn sẽ giải thích instruction invokevirtual, invokespecial, invokestatic và invokeinterface được chọn theo ngữ cảnh nào?
Bạn phân tích khi nào invokedynamic được dùng cho lambda hoặc dynamic language support như thế nào?
Bạn sẽ tìm bootstrap methods liên quan invokedynamic trong output javap để hiểu cơ chế liên kết ra sao?
Bạn phân biệt bytecode do javac tạo ra với machine code do JIT compiler có thể tạo tại runtime như thế nào?
Bạn sẽ xác định exception table trong Code attribute biểu diễn các catch handlers như thế nào?
Bạn mô tả StackMapTable hỗ trợ bytecode verification theo kiểu dữ liệu trên operand stack như thế nào?
Bạn sẽ dùng LineNumberTable để đối chiếu bytecode offset với dòng source khi debug như thế nào?
Bạn phân biệt LocalVariableTable với MethodParameters trong mức độ lưu tên biến và tham số như thế nào?
Bạn sẽ giải thích Signature attribute lưu metadata generic types nhưng không thay đổi erasure runtime như thế nào?
Bạn phân tích vì sao annotation có RetentionPolicy.SOURCE không xuất hiện trong runtime-visible class attributes ra sao?
Bạn sẽ xác định khác biệt giữa RuntimeVisibleAnnotations và RuntimeInvisibleAnnotations qua javap như thế nào?
Bạn sẽ dùng javap để kiểm tra record attributes hoặc permitted subclasses của sealed classes ra sao?
Bạn mô tả ACC_SYNTHETIC và ACC_BRIDGE trong class/method flags biểu thị compiler-generated members như thế nào?
Bạn sẽ xác định vì sao Java compiler tạo accessor hoặc synthetic constructions trong một phiên bản JDK nhưng không tạo ở bản khác ra sao?
Bạn phân biệt class-file bytecode verification với Java compile-time semantic checking theo giới hạn nào?
Bạn sẽ dùng ASM library để đọc hoặc biến đổi bytecode khi javap không đủ nhu cầu tự động hóa ra sao?
Bạn phân tích rủi ro ASM transformation làm sai stack frames hoặc constant pool dẫn tới VerifyError như thế nào?
Bạn sẽ đánh giá tác động của bytecode instrumentation do JaCoCo hoặc agent tới kích thước và nội dung class files như thế nào?
Bạn sẽ kiểm tra một JAR có nhiều bản class trong META-INF/versions bằng công cụ bytecode nào?
Bạn phân biệt checksum class file với hành vi tương đương về ngữ nghĩa khi compiler version thay đổi ra sao?
Bạn sẽ thiết kế test bytecode contract không quá phụ thuộc thứ tự instruction do compiler tối ưu như thế nào?
Bạn sẽ sử dụng jdeps kết hợp javap để đánh giá thư viện phụ thuộc API nội bộ JDK như thế nào?
Bạn sẽ quyết định khi nào phân tích .class artifact trực tiếp giúp tìm lỗi phát hành mà test mã nguồn không phát hiện ra sao?
Bạn giải thích -Xlint của javac hỗ trợ phát hiện những loại cảnh báo có giá trị trong code review như thế nào?
Bạn sẽ kết hợp -Xlint:unchecked với -Werror để đặt chất lượng compile-time như thế nào?
Bạn phân biệt compiler error với compiler warning và annotation processor warning theo ảnh hưởng đến exit code ra sao?
Bạn sẽ xác định khi nào sử dụng @SuppressWarnings hợp lý và cách tránh che tất cả cảnh báo mới như thế nào?
Bạn mô tả cách bật -Xdiags:verbose giúp hiểu nguyên nhân type inference hoặc overload resolution thất bại ra sao?
Bạn sẽ phân biệt first compiler error với hàng loạt cascading errors sau nó trong một build log dài như thế nào?
Bạn sẽ tìm nguyên nhân package does not exist bằng cách kiểm tra classpath và dependency resolution như thế nào?
Bạn phân tích vì sao cannot find symbol có thể xuất phát từ annotation processor chưa chạy chứ không chỉ thiếu import ra sao?
Bạn sẽ xác định lúc nào lỗi module not found xuất phát từ module path và lúc nào từ module-info.java requires ra sao?
Bạn sẽ kiểm tra lỗi package is declared in module but module does not read it bằng công cụ hoặc flag nào ra sao?
Bạn sẽ chẩn đoán cannot access class file có wrong version từ JDK hoặc dependency versions như thế nào?
Bạn sẽ xác định lý do IDE không báo lỗi nhưng Maven build lại thiếu generated sources ra sao?
Bạn phân biệt clean build với incremental build trong cách phát hiện stale .class hoặc generated source files như thế nào?
Bạn sẽ dùng Maven Compiler Plugin hoặc Gradle compileJava logging để xem effective compiler options ra sao?
Bạn phân tích nguy cơ compiler options được IDE tự thêm nhưng build CI không có dẫn đến chênh lệch như thế nào?
Bạn sẽ xác định dependency xuất hiện trong testCompileClasspath nhưng không có trong compileClasspath theo Gradle như thế nào?
Bạn phân biệt Maven compile và test-compile goals theo nguồn Java và dependency scopes nào?
Bạn sẽ thiết kế cache key cho Java compilation dựa trên compiler version, sources, flags và dependencies như thế nào?
Bạn phân tích vì sao đổi annotation processor version phải invalidate generated sources hoặc incremental build state ra sao?
Bạn sẽ phân biệt lỗi Gradle daemon dùng JDK khác với JDK toolchain của JavaCompile tasks ra sao?
Bạn sẽ so sánh java -version, javac -version, JAVA_HOME và build toolchain trong một incident report như thế nào?
Bạn phân tích vì sao default encoding khác giữa OS có thể làm lỗi illegal character khi compile nguồn tiếng Việt ra sao?
Bạn sẽ bật deterministic source encoding để không phụ thuộc charset của máy developer như thế nào?
Bạn sẽ chẩn đoán lỗi duplicate class xuất hiện vì hai generated source directories cùng được thêm vào build ra sao?
Bạn sẽ xác định khi nào cần chạy javac trực tiếp trên một tập source nhỏ để tách lỗi build tool khỏi lỗi compiler ra sao?
Bạn sẽ phân biệt compile failure do thiếu memory với lỗi semantic analysis bằng thông tin log nào?
Bạn sẽ thiết kế CI lưu compiler diagnostics và effective build environment mà không tiết lộ secret tokens ra sao?
Bạn phân tích rủi ro build script tải compiler plugin hoặc annotation processor từ nguồn không tin cậy như thế nào?
Bạn sẽ chuẩn hóa quy trình tái hiện build failure từ local, clean CI runner và pinned dependencies ra sao?
Bạn sẽ đề xuất checklist phát hành bảo đảm artifact JAR thực sự chứa .class files đúng module path, version và nguồn gốc như thế nào?
Nếu javac báo cannot find symbol với class đã được annotation processor tạo ở máy khác, bạn sẽ kiểm tra processor path và generated sources ra sao?
Nếu IDE compile thành công nhưng CI báo annotation processing not enabled, bạn sẽ xác minh compiler options và JDK version như thế nào?
Nếu một source dùng API Java mới nhưng sản phẩm phải chạy trên JDK cũ, bạn sẽ kiểm tra --release thay vì chỉ -target ra sao?
Nếu runtime báo UnsupportedClassVersionError sau khi build, bạn sẽ đọc class file major version và đối chiếu toolchains như thế nào?
Nếu chuyển dependency JAR từ classpath sang module path gây package is not visible, bạn sẽ kiểm tra exports và requires như thế nào?
Nếu hai JAR chứa cùng class nhưng build dùng nhầm bản cũ, bạn sẽ kiểm tra classpath order và dependency graph ra sao?
Nếu compile trên Windows thất bại vì classpath separator sai, bạn sẽ sửa cách build tool dựng arguments như thế nào?
Nếu processor tạo source mới nhưng round tiếp theo không nhận diện được annotation, bạn sẽ kiểm tra Filer và RoundEnvironment như thế nào?
Nếu build incremental vẫn thấy generated classes đã bị xóa trong source, bạn sẽ tìm stale artifacts và dependency cache như thế nào?
Nếu generic overload sinh name clash do erasure, bạn sẽ thiết kế lại method signatures như thế nào?
Nếu một lambda invocation trở nên ambiguous sau khi thêm overload, bạn sẽ phân tích target types và compiler resolution ra sao?
Nếu JavaCompiler API trả false nhưng UI chỉ hiện build failed, bạn sẽ lấy DiagnosticCollector để hiển thị lỗi có vị trí như thế nào?
Nếu ứng dụng compile mã người dùng trong bộ nhớ và annotation processor thực thi code lạ, bạn sẽ thay đổi ranh giới cô lập như thế nào?
Nếu custom JavaFileManager không thu được output class bytes, bạn sẽ kiểm tra getJavaFileForOutput và openOutputStream ra sao?
Nếu custom ClassLoader báo LinkageError khi nạp class vừa compile, bạn sẽ kiểm tra binary name và class loader identity như thế nào?
Nếu javap cho thấy ACC_BRIDGE method ngoài dự kiến, bạn sẽ liên hệ nó với generic overrides như thế nào?
Nếu bytecode instrumentation tạo VerifyError ở runtime, bạn sẽ kiểm tra StackMapTable và tính hợp lệ của bytecode bằng công cụ nào?
Nếu Java package tests PASS nhưng artifact release thiếu module-info.class, bạn sẽ kiểm tra source set và jar packaging ra sao?
Nếu Gradle và Maven tạo class files khác nhau từ cùng source, bạn sẽ so sánh javac flags, JDK, processors và reproducible build settings như thế nào?
Nếu một Java project cần compile in-memory, hỗ trợ JPMS, nhiều JDK targets và chẩn đoán bytecode, bạn sẽ thiết kế JavaCompiler API workflow, configuration, QA và CI như thế nào?
