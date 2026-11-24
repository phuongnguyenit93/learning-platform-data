# logContainerConfig

In Spring Kafka, the listener container manages consumer lifecycle, calls `poll()`, dispatches records to listeners, and coordinates acknowledgments with the consumer group. When an application starts, containers are built from Spring Boot configuration, listener container factories, and Kafka consumer factories. When values come from multiple sources, determining which configuration a container is actually using can take time.

`logContainerConfig` is an option that causes the listener container to log an INFO-level message summarizing the container's configuration properties. When enabled, each listener container logs this summary during initialization. This is a useful diagnostic tool when verifying applied configuration, especially in applications with multiple `@KafkaListener` endpoints, multiple container factories, or multiple deployment environments.

This option does not change how consumers read records, commit offsets, or participate in consumer groups. It simply adds configuration information to logs so operations teams can inspect and verify it easily.

## 1. What is logContainerConfig?

`logContainerConfig` is a property on `ContainerProperties` in Spring Kafka. When set to `true` and the `INFO` log level is enabled for the relevant logger, the listener container logs a summary of its configuration.

Key characteristics:

- Available since Spring Kafka 2.1.1.
- Default value on `ContainerProperties` is `false`.
- Logged at `INFO` level.
- Each listener container logs configuration info upon initialization.
- Content is a summary of container properties for configuration diagnostics.

`logContainerConfig` is not a Kafka broker setting and not a consumer property sent to brokers. It is a Spring Kafka container property. Therefore, do not place it in `spring.kafka.consumer.properties` or pass it as a Kafka client property.

~~~text
Spring Boot configuration
          |
          v
Listener container factory
          |
          v
ContainerProperties
          |
          +---- logContainerConfig = true
          |
          v
Listener container starts
          |
          v
INFO log: container configuration summary
~~~

## 2. Enabling via Spring Boot application.yml

For the default listener container factory auto-configured by Spring Boot, the simplest approach is setting the property:

~~~yaml
spring:
  kafka:
    listener:
      log-container-config: true
~~~

The kebab-case property in YAML is `log-container-config`; Spring Boot binds it to the `logContainerConfig` property of listener configuration.

If using `application.properties`, the equivalent setting is:

~~~properties
spring.kafka.listener.log-container-config=true
~~~

When the application starts and containers are created, Spring Kafka logs the configuration message at `INFO` level, provided the logger permits that level.

### 2.1. Enabling per profile

You can enable config logging in development or staging without turning it on by default in every environment:

~~~yaml
# application-staging.yml
spring:
  kafka:
    listener:
      log-container-config: true
~~~

In production, deciding whether to enable or disable it should weigh diagnostic need, container count, and logging policies. If an application has many high-concurrency listeners, config logs from every child container can increase startup log lines. Check actual log volume before enabling broadly.

### 2.2. Verifying property binding

After deployment, verify:

1. The right Spring profile is active.
2. The expected configuration file is loaded in the runtime environment.
3. The property is not overridden by environment variables or command-line arguments.
4. Whether the application uses the default listener container factory or a custom factory.
5. The relevant logger permits `INFO`.

If the property is set yet no log appears, do not immediately conclude Spring Kafka lacks support for the feature. The container may not have initialized yet, the setting may apply to a different factory, or the log level may be filtering out the message.

## 3. Enabling directly on ContainerProperties

If the application creates listener containers manually or wants Java-based configuration control, set the property directly:

~~~java
ContainerProperties containerProperties =
        new ContainerProperties("orders");

containerProperties.setGroupId("billing-service");
containerProperties.setLogContainerConfig(true);

KafkaMessageListenerContainer<String, OrderCreated> container =
        new KafkaMessageListenerContainer<>(
                consumerFactory,
                containerProperties);
~~~

This example illustrates a directly created container. In real applications, `consumerFactory`, key/value types, and the listener must be fully configured before the container starts.

You can read back the value:

~~~java
boolean logConfig =
        containerProperties.isLogContainerConfig();
~~~

The getter and setter belong to `ContainerProperties`. Set the value before the container starts running so the info is logged during initialization.

## 4. Enabling for factory-created containers

Applications using `@KafkaListener` typically create containers via `ConcurrentKafkaListenerContainerFactory`. You can configure factory-created containers with a customizer:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);

    factory.setContainerCustomizer(container ->
            container.getContainerProperties()
                    .setLogContainerConfig(true));

    return factory;
}
~~~

`ContainerCustomizer` lets you customize the container after the factory creates and configures it. This API has been available since Spring Kafka 2.3.4. Check your project's dependency version and container type.

If the application already has a custom factory, add the property to the existing factory instead of creating a second factory just to enable logging. This avoids unintended differences in consumer factory, error handler, converter, interceptor, transaction manager, or concurrency.

### 4.1. Note on multiple listener container factories

An application may define multiple factories, for example:

- Factory for order topics with high concurrency.
- Factory for audit topics with low concurrency.
- Factory for batch listeners.
- Factory with dedicated transactions or error handlers.

The `spring.kafka.listener.log-container-config` property belongs to Spring Boot listener configuration and applies to the auto-configured factory via Boot's binding mechanism. If the application declares its own custom factories, verify whether those custom factories receive that configuration. When certainty is needed, set `setLogContainerConfig(true)` on `ContainerProperties` or use `ContainerCustomizer` on each corresponding factory.

Do not check only one listener and assume all containers have it enabled. Each listener can specify a different `containerFactory` in its annotation:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders",
        containerFactory = "orderKafkaListenerContainerFactory")
public void listen(OrderCreated event) {
    orderService.process(event);
}
~~~

## 5. Log content and information scope

The logged message is a summary of container configuration. It helps identify Spring Kafka settings the container is using, such as properties on `ContainerProperties` and listener-container-related details.

When reading logs, cross-check information groups that affect operations:

| Group | Content to verify |
|---|---|
| Listener identity | Bean/container name, listener ID, or container identifying info |
| Topic subscription | Specified topics, topic patterns, or partitions |
| Consumer group | Group ID used by the listener |
| Acknowledgement | Ack mode and commit-related settings |
| Polling | Poll timeout, concurrency, and related container properties |
| Error handling | Error handler or related recovery settings if shown in logs |
| Transaction | Container transaction configuration if applied |
| Monitoring | Idle event, monitor, and no-poll threshold properties if shown |

Do not assume this message is a full dump of all configuration across the whole system. `logContainerConfig` focuses on listener container configuration; it does not replace checking full `ConsumerFactory`, Kafka client properties, broker configuration, ACLs, topic configuration, or runtime state.

In particular, config logs do not prove brokers accepted every value, topics exist, consumers have read permissions, or partitions are assigned. To verify those conditions, combine startup logs with consumer group state, broker metrics, ACLs, and actual runtime behavior.

## 6. Conditions for the log to appear

Two important conditions apply:

1. `logContainerConfig` must be `true` on the initialized container.
2. The logger must allow `INFO` level.

Example log level configuration:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.kafka: INFO
~~~

The exact logger emitting the message may vary by version and implementation. To filter precisely, observe the logger name in actual log lines and configure that category accordingly. Do not raise the entire application's logging to `DEBUG` just to see this message.

If the relevant logger only permits `WARN` or `ERROR`, the `INFO`-level message will not appear even when the property is enabled.

### 6.1. When is the log written?

This is a configuration log during container initialization/startup, not a repeating log per record or per poll. Nor is it a real-time updating configuration dashboard.

If configuration changes while the application is running, the old log still reflects configuration at container initialization time. To get logs for new configuration, apply changes via proper lifecycle and re-initialize the container. Do not restart containers solely to emit logs unless operationally necessary.

## 7. Distinguishing from other Spring Kafka logs

`logContainerConfig` is easily confused with other logging options. They serve distinct purposes:

| Option | Purpose | When to use |
|---|---|---|
| `logContainerConfig` | Logs listener container configuration summary at INFO on initialization | Verify active container configuration |
| `commitLogLevel` | Selects log level for offset-commit-related messages | Investigate commit timing and outcomes |
| Kafka client loggers | Logs internal activity of consumer/producer clients | Investigate protocol, coordinator, network, or client behavior |
| `missingTopicsFatal` | Decides whether the container fails startup when configured topics do not exist | Control startup behavior when topics are missing |
| Application logs | Logs business info emitted explicitly by the application | Track event IDs, processing outcomes, and business errors |

For example, `commitLogLevel` controls the log level of offset commits; it does not enable container config logging. Conversely, `logContainerConfig` does not cause offset commits to be logged at INFO and does not alter commit semantics.

If commit investigation is needed, configure commit logging separately:

~~~java
containerProperties.setCommitLogLevel(
        LogIfLevelEnabled.Level.INFO);
~~~

APIs and enums must match your Spring Kafka version. Increase commit log level only when needed, because logging every commit can generate heavy log volume at high throughput.

## 8. Using logContainerConfig in deployment workflows

An effective practice is enabling config logging during release verification or when investigating differences across environments.

Reference workflow:

1. Identify the listener to inspect and the factory it uses.
2. Enable `log-container-config` for that factory.
3. Start the application or container per deployment procedure.
4. Locate the config log for the exact listener/container.
5. Verify topics, group ID, ack mode, concurrency, and required operational properties against expectations.
6. If discrepancies appear, trace the value source across YAML, profiles, environment variables, factory customizers, or annotations.
7. Fix the configuration source and redeploy.
8. Archive logs or verification output per change management procedures if needed.

In applications with many listeners, you can enable it in staging to establish a configuration baseline for each container. Once verified, you can disable it again if startup logs are too noisy or production policy does not require retaining this output.

## 9. Checking overridden configuration

Spring Boot can receive configuration from multiple sources. A value in `application.yml` can be overridden by:

- Profile-specific configuration files.
- Environment variables.
- Java system properties.
- Command-line arguments.
- Settings configured directly in beans.
- `ContainerCustomizer` or container-creation code.

For instance, YAML sets `log-container-config: true`, yet a custom factory subsequently calls `setLogContainerConfig(false)`. In that case, the log may not appear for containers created by the custom factory.

When investigating, trace in exact container-creation order:

~~~text
External configuration
        |
        v
Spring Boot KafkaProperties
        |
        v
Auto-configured listener factory
        |
        +---- Custom factory?
        |         |
        |         v
        |    ContainerCustomizer
        |
        v
ContainerProperties
        |
        v
Container startup
~~~

With custom factories, inspect the final configuration after customizers have run. Seeing a property in YAML only proves that configuration source holds that value, not that the final container keeps the same value.

## 10. Performance and log volume impact

`logContainerConfig` logs only one configuration message during container initialization. It does not log per record, so runtime cost is typically negligible compared to message-path logging.

However, startup log lines scale with the number of listener containers created. With a high-concurrency `ConcurrentMessageListenerContainer`, the container can create multiple child containers/consumer threads; observe actual message counts when enabling the setting.

Considerations:

- Enabling in staging or during configuration investigations can be very helpful.
- Keeping it enabled long-term in production can still be acceptable if container counts are modest and logs are well managed.
- Avoid enabling broad `DEBUG` categories simultaneously just to hunt for this message.
- Do not leave startup logs repeating continuously due to app restarts or unintended container stop/start cycles without investigating the root cause.
- Check retention, access controls, and log storage policies.

Do not treat `logContainerConfig` as a log-reduction or log-volume control tool. It is an on/off toggle for a specific type of diagnostic output.

## 11. Security and managing configuration logs

Operational logs can contain topic names, group IDs, client IDs, listener IDs, and deployment details. These details help operators, yet can also expose system topology if logs are broadly shared.

Apply these principles:

- Restrict log read access by role.
- Never manually inject passwords, SASL secrets, tokens, or credentials into configuration logs.
- Do not assume every version or custom `toString()` masks sensitive fields; inspect actual output.
- Apply retention and masking per organizational security policy.
- When sharing logs externally for troubleshooting, strip sensitive info and unnecessary internal identifiers.

If logs expose sensitive data due to custom code or config wrappers, fix that logging or data source. Disabling `logContainerConfig` is only a stopgap if the root leak sits in another logger.

## 12. Diagnosing when logs do not appear

If `log-container-config` is enabled yet no message appears, check in order:

1. Confirm the final value of `ContainerProperties.isLogContainerConfig()` is `true`.
2. Confirm the intended listener container was actually created and started.
3. Confirm the listener is using the exact factory you configured.
4. Confirm the logger allows `INFO`.
5. Check whether log aggregators filter categories, messages, or startup logs.
6. Check whether the container was created before the setting was applied.
7. If using a custom factory, inspect `ContainerCustomizer` and any code resetting properties.
8. Confirm your Spring Kafka version supports this property.

### 12.1. Log appears but values differ from expectations

If the message shows wrong settings:

1. Find the original property across active config files and profiles.
2. Check environment variables and command-line arguments.
3. Check which factory created the listener.
4. Check customizers and code calling setters.
5. Check the `@KafkaListener` annotation, especially `groupId`, `id`, `containerFactory`, and subscriptions.
6. Fix the correct configuration source, then recreate the container and verify the new log.

Do not tweak a consumer property arbitrarily just to make the log look right. Determine which value genuinely needs changing and its impact on consumer groups, offsets, or partition assignments.

### 12.2. Log appears multiple times

The message can appear multiple times when:

- The application has multiple listener containers.
- A concurrent listener container creates multiple child containers.
- Containers are stopped and started again.
- The application restarts or performs a rolling update.

Counting listener beans is insufficient to predict line counts. Match container names, listener IDs, and consumer thread names in logs to identify which container each message belongs to.

## 13. Complete configuration example

A simple Spring Boot configuration:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-service
      enable-auto-commit: false
    listener:
      concurrency: 3
      ack-mode: record
      log-container-config: true

logging:
  level:
    org.springframework.kafka: INFO
~~~

Listener:

~~~java
@Component
public class BillingListener {

    @KafkaListener(
            id = "billingOrders",
            topics = "orders")
    public void handle(OrderCreated event) {
        billingService.process(event);
    }
}
~~~

In this example, Spring Boot configures the default listener factory based on `spring.kafka.listener.*`. When the listener container initializes, it logs a configuration summary at INFO. `logContainerConfig` does not alter `ack-mode`, `concurrency`, group ID, or subscription; those properties are set separately in YAML and the annotation.

If the application declares a separate `ConcurrentKafkaListenerContainerFactory`, configure `setLogContainerConfig(true)` or a customizer on that factory and confirm the listener uses the right factory name.

## 14. Verification exercise

A short exercise helps clarify the option's scope:

1. Create a Spring Boot app with one `@KafkaListener`.
2. Set `spring.kafka.listener.log-container-config: false`, start up, and save logs.
3. Change it to `true`, restart, and locate the INFO configuration message.
4. Change the relevant logger to `WARN`, restart, and observe the INFO message being filtered out.
5. Restore the logger to INFO, change `concurrency` from 1 to 3, and observe the containers/threads created.
6. Add a custom factory, configure logging separately, and verify which listener uses which factory.
7. Override a property via an environment variable to observe configuration sources overriding YAML.
8. Compare logs after each startup and record the source of the final value.

This exercise verifies three things: whether the property binds, whether the logger allows INFO, and whether the final container receives the expected configuration.

## 15. Operations checklist

### Configuration

- [ ] Identified the Spring Kafka and Spring Boot versions in use.
- [ ] Enabled the proper `spring.kafka.listener.log-container-config` property or corresponding setter.
- [ ] Verified the value is set on the right listener container factory.
- [ ] Custom factories/customizers do not overwrite it unintentionally.
- [ ] Relevant logger permits INFO level.

### Log inspection

- [ ] Message appears when containers initialize.
- [ ] Mapped each message to its corresponding listener/container.
- [ ] Verified required topic, group ID, concurrency, and ack mode.
- [ ] Understood the log is a configuration summary, not full broker or runtime state.
- [ ] Logs do not expose credentials or sensitive data.

### Operations

- [ ] Selected appropriate environments and duration for enabling.
- [ ] Monitored log volume when there are many listeners/concurrency.
- [ ] Upgrade procedures re-verify logger names and output if versions change.
- [ ] Runbook exists to trace property sources when actual configuration differs from expectations.

## Conclusion

`logContainerConfig` is a simple yet useful diagnostic toggle in Spring Kafka. When enabled, each listener container logs a configuration summary at INFO level during initialization; by default this property is `false`. Spring Boot supports configuring it via `spring.kafka.listener.log-container-config`, while applications creating containers manually can call `ContainerProperties.setLogContainerConfig(true)`. Use this message to confirm final configuration, verify the right factory and profile, and combine it with consumer group state, broker logs, and metrics during incident investigations. It provides evidence of container configuration at startup, without replacing checks of Kafka's actual operational state.

## References

- [Spring Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring Kafka — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
