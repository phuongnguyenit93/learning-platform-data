# Distinguishing Calling the shutdown Endpoint from Web Server Graceful Shutdown Configuration

When you need to stop a Spring Boot instance serving requests, there are two separate decisions. **Which signal starts closing the application?** And **how does the web server handle in-flight requests while closing?** The `shutdown` endpoint is one way to send the signal. `server.shutdown` chooses how the embedded web server stops after the application begins closing.

The properties and examples in this guide use Spring Boot **3.3.x**.

## The shutdown Endpoint Initiates Application Shutdown

With Actuator, `POST /actuator/shutdown` requests closing the `ApplicationContext`. Spring Boot 3.3 disables this endpoint by default. To invoke it over HTTP, the endpoint must be enabled and included in the web exposure list.

```properties
management.endpoint.shutdown.enabled=true
management.endpoints.web.exposure.include=health,shutdown
```

The `/actuator/shutdown` path assumes the default Actuator base path. If the application has a separate management port, send the request to that port. In deployment environments, restrict permission to call the endpoint to authorized operational systems because this operation stops the application instance. With Spring Security, `POST` requests may also be rejected by CSRF checks depending on configuration.

A successful response is HTTP 200 with the `message` field set to `Shutting down, bye...` in the example's default configuration. The endpoint initiates shutdown on a separate thread. Therefore, status 200 reports that the operation was accepted, while waiting for in-flight requests and closing resources happens afterward. To confirm the application has stopped, check the process or shutdown completion logs.

## Graceful Shutdown Governs How the Web Server Stops

The following configuration instructs the embedded web server to stop accepting new requests and give in-flight requests time to complete when the application context closes.

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=15s
```

`spring.lifecycle.timeout-per-shutdown-phase` is the timeout **for each shutdown phase** of lifecycle components, including the web server shutdown phase. Total application shutdown time also depends on other phases. A request taking longer than the timeout may be aborted when the server proceeds with stopping. When using `server.shutdown=immediate`, the server skips the wait period for in-flight requests.

How new requests are rejected depends on the server. With Spring Boot 3.3, Tomcat, Jetty, and Reactor Netty stop accepting new requests at the network layer. Undertow may still accept connections and return HTTP 503. What clients observe also depends on connection reuse and intermediaries. Verify which server the application is running when interpreting error codes.

| Scenario | Trigger starting shutdown | In-flight request handling |
| --- | --- | --- |
| Endpoint exposed, `server.shutdown=immediate` | Send `POST` to Actuator | May be aborted when the server stops. |
| Endpoint exposed, `server.shutdown=graceful` | Send the same `POST` request | Given time to complete during the web shutdown phase. |
| Endpoint disabled, `server.shutdown=graceful` | Another trigger closes the context, such as `SIGTERM` on Unix with the JVM shutdown hook active | Still given time to complete during the web shutdown phase. |
| `server.shutdown=graceful` set and application running normally | No trigger has closed the context yet | The server continues serving as normal. |

When the operating system forcefully terminates the process, such as `SIGKILL` on Unix, the JVM cannot run its shutdown hook. In deployments, the termination grace period granted by the platform must be sufficient for the application's shutdown phases. To reduce new requests reaching a shutting-down instance, the routing layer must also stop sending traffic to that instance.

## Practice with Spring Boot 3.3 and Embedded Tomcat

The example runs on the loopback address. The `GET /slow` endpoint takes about eight seconds to respond, long enough to observe an in-flight request when the shutdown command is sent. Save the code to `ShutdownDemo.java`.

```java
package demo.shutdown;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ShutdownDemo {
    public static void main(String[] args) {
        SpringApplication.run(ShutdownDemo.class, args);
    }

    @GetMapping("/slow")
    public String slow() throws InterruptedException {
        System.out.println("WORK_STARTED");
        Thread.sleep(8_000);
        System.out.println("WORK_FINISHED");
        return "work completed";
    }
}
```

Place the following `pom.xml` next to the Java file. `spring-boot-starter-web` provides embedded Tomcat and `spring-boot-starter-actuator` provides management endpoints.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo.shutdown</groupId>
    <artifactId>shutdown-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
            <version>3.3.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
            <version>3.3.0</version>
        </dependency>
    </dependencies>
</project>
```

Use Maven to download dependencies and JDK 17 or later to compile. Run the application in the first window, assuming local port `18089` is free.

```bash
mvn -q dependency:copy-dependencies -DincludeScope=runtime -DoutputDirectory=lib
javac -cp "lib/*" -d out ShutdownDemo.java
java -cp "out:lib/*" demo.shutdown.ShutdownDemo --server.address=127.0.0.1 --server.port=18089 --management.endpoint.shutdown.enabled=true --management.endpoints.web.exposure.include=health,shutdown --server.shutdown=graceful --spring.lifecycle.timeout-per-shutdown-phase=15s
```

On Windows, change the runtime classpath to `"out;lib/*"` and use `curl.exe` if PowerShell aliases `curl` to another command.

1. In the second window, start the slow request.

   ```bash
   curl -sS -w "\nHTTP %{http_code}\n" http://127.0.0.1:18089/slow
   ```

2. As soon as the application window prints `WORK_STARTED`, immediately run the following command from the third window before `WORK_FINISHED` appears.

   ```bash
   curl -sS -w "\nHTTP %{http_code}\n" -X POST http://127.0.0.1:18089/actuator/shutdown
   ```

3. With a 15-second timeout, the shutdown command returns HTTP 200 and the in-flight `GET /slow` request completes. The two lines printed by the Java code itself, interspersed with Spring Boot logs, are:

   ```text
   WORK_STARTED
   WORK_FINISHED
   ```

   The window calling `GET /slow` receives:

   ```text
   work completed
   HTTP 200
   ```

4. Restart with the same `java` command, changing only `--server.shutdown=immediate`, and repeat. The `POST` command can still return HTTP 200 while the in-flight slow request is aborted. Next, try `graceful` with `--spring.lifecycle.timeout-per-shutdown-phase=1s`. If the shutdown command arrives when the request has more than one second of work left, the timeout expires before the request completes. The exact error message on the client depends on how the connection closes.

If `POST` returns 404, check that the endpoint is enabled, exposed over web, and using the right port and management path. If it returns 401 or 403, check credentials, invocation permissions, and CSRF configuration accordingly. If `POST` succeeds but in-flight requests are aborted, check the shutdown mode, phase timeout, and whether the platform is terminating the process early.

Spring Boot 3.3 documentation. [shutdown endpoint REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/shutdown.html) · [Enabling and exposing Actuator endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html) · [Graceful shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)
